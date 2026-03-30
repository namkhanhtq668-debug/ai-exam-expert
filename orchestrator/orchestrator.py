from __future__ import annotations

import copy
import json
import logging
from os import getenv
from time import perf_counter
from typing import Any

from agents.critic_agent import CriticAgent
from agents.curriculum_alignment_agent import CurriculumAlignmentAgent
from agents.generation_agent import GenerationAgent
from agents.planner_agent import PlannerAgent
from agents.refinement_agent import RefinementAgent
from agents.validation_agent import ValidationAgent
from clients.base_llm_client import BaseLLMClient
from orchestrator.agent_result import AgentResult
from orchestrator.workflow_state import WorkflowState
from services.audit_service import AuditService
from services.compliance_service import ComplianceService
from services.retry_service import RetryService
from services.ui_helpers import chunk_text, simple_retrieve


class MultiAgentOrchestrator:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        schema,
        max_retries: int = 3,
        *,
        audit_log_file: str | None = None,
        audit_enabled: bool | None = None,
    ):
        self.llm_client = llm_client
        self.generation_agent = GenerationAgent(llm_client)
        self.validation_agent = ValidationAgent(schema)
        self.refinement_agent = RefinementAgent(llm_client)
        self.planner_agent = PlannerAgent(llm_client)
        self.curriculum_alignment_agent = CurriculumAlignmentAgent(schema)
        self.critic_agent = CriticAgent(llm_client)
        self.compliance_service = ComplianceService(schema, compliance_threshold=0.7)
        self.max_retries = max(1, max_retries)
        self.retry_service = RetryService(max_retries=self.max_retries, base_delay=1.0)
        self.retrieval_min_confidence = 0.55
        self.final_approval_min_confidence = 0.75
        self.fast_path_min_confidence = 0.86
        self.max_refine_retries = 1
        self._plan_cache: dict[str, dict[str, Any]] = {}
        self._retrieval_cache: dict[str, dict[str, Any]] = {}
        self._generation_cache: dict[str, dict[str, Any]] = {}
        self._configure_model_preferences()

        resolved_log_file = audit_log_file or getenv("AI_EXAM_AUDIT_LOG_FILE") or "workflow_audit.jsonl"
        resolved_enabled = audit_enabled
        if resolved_enabled is None:
            env_enabled = getenv("AI_EXAM_AUDIT_ENABLED")
            if env_enabled is not None:
                resolved_enabled = env_enabled.strip().lower() not in {"0", "false", "no", "off"}
        if resolved_enabled is None:
            resolved_enabled = True
        self.audit_service = AuditService(log_file=resolved_log_file, enabled=resolved_enabled)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.last_state: WorkflowState | None = None
        self.last_run_summary: dict[str, object] | None = None

    def _record(self, state: WorkflowState, agent_name: str, result, duration_ms: float | None = None):
        state.record(agent_name, result, duration_ms=duration_ms)
        self.audit_service.record_agent_step(
            state.trace_id,
            agent_name,
            status=getattr(result, "status", None),
            duration_ms=duration_ms,
            attempt=state.attempt_count,
            metadata={
                "stage": state.stage,
                "attempt_count": state.attempt_count,
                "agent_result": getattr(result, "metadata", {}) or {},
            },
            confidence=getattr(result, "confidence", None),
            issues=list(getattr(result, "issues", []) or []),
            next_action=getattr(result, "next_action", None),
        )
        self.logger.info(
            "trace=%s stage=%s agent=%s status=%s duration_ms=%.3f",
            state.trace_id,
            state.stage,
            agent_name,
            getattr(result, "status", None),
            duration_ms or 0.0,
        )
        return result

    def _run_agent(self, state: WorkflowState, agent_name: str, agent, payload):
        started = perf_counter()
        try:
            result = agent.execute(payload)
        except Exception as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            state.errors.append(f"{agent_name}: {exc}")
            self.audit_service.record_exception(
                state.trace_id,
                agent_name,
                exc,
                stage=state.stage,
                duration_ms=duration_ms,
            )
            result = agent.fail(
                [str(exc)],
                output=payload,
                next_action="retry",
                confidence=0.0,
                metadata={
                    "agent": agent_name,
                    "exception_type": type(exc).__name__,
                    "stage": state.stage,
                },
            )
        duration_ms = (perf_counter() - started) * 1000.0
        return self._record(state, agent_name, result, duration_ms=duration_ms)

    @staticmethod
    def _unwrap(result):
        return result.output if isinstance(result, AgentResult) else result

    @staticmethod
    def _coerce_text(value: Any) -> str:
        return "" if value is None else str(value).strip()

    def _configure_model_preferences(self) -> None:
        provider = getattr(self.llm_client, "provider", "").strip().lower()
        default_small = "gpt-4o-mini" if provider == "openai" else "gemini-2.0-flash"
        default_large = "gpt-4o" if provider == "openai" else getattr(self.llm_client, "model_name", default_small)
        small_model = getenv("AI_EXAM_SMALL_MODEL") or default_small
        large_model = getenv("AI_EXAM_LARGE_MODEL") or default_large

        setattr(self.llm_client, "model_name", large_model)
        setattr(self.llm_client, "planner_model_name", small_model)
        setattr(self.llm_client, "alignment_model_name", small_model)
        setattr(self.llm_client, "critic_model_name", small_model)
        setattr(self.llm_client, "generation_model_name", large_model)
        setattr(self.llm_client, "refine_model_name", large_model)

    @staticmethod
    def _make_cache_key(value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)

    def _cache_get(self, cache: dict[str, dict[str, Any]], key: str) -> dict[str, Any] | None:
        cached = cache.get(key)
        return copy.deepcopy(cached) if isinstance(cached, dict) else None

    def _cache_set(self, cache: dict[str, dict[str, Any]], key: str, value: dict[str, Any]) -> dict[str, Any]:
        snapshot = copy.deepcopy(value)
        cache[key] = snapshot
        return snapshot

    def _is_fast_path_candidate(self, input_data: dict[str, Any], planned_data: dict[str, Any], generated_data: dict[str, Any]) -> bool:
        if input_data.get("strict_alignment") or input_data.get("expected_risk"):
            return False
        if not isinstance(generated_data, dict):
            return False
        question = self._coerce_text(generated_data.get("question"))
        explanation = self._coerce_text(generated_data.get("explanation"))
        answer = self._coerce_text(generated_data.get("answer")).upper()
        options = generated_data.get("options") or []
        curriculum_context = dict(planned_data.get("curriculum_context") or input_data.get("curriculum_context") or {})
        if not question or not explanation or answer not in {"A", "B", "C", "D"}:
            return False
        if not isinstance(options, list) or len(options) != 4:
            return False
        return bool(curriculum_context.get("topic") and curriculum_context.get("lesson") and curriculum_context.get("yccd"))

    def _build_curriculum_corpus(self, payload: dict[str, Any]) -> list[str]:
        corpus_parts: list[str] = []
        plan = dict(payload.get("plan") or {})
        yccd_item = dict(payload.get("yccd_item") or {})
        curriculum_context = dict(payload.get("curriculum_context") or plan.get("curriculum_context") or {})

        for source in (
            yccd_item.get("mon"),
            yccd_item.get("lop"),
            yccd_item.get("chu_de"),
            yccd_item.get("bai"),
            yccd_item.get("yccd"),
            curriculum_context.get("subject"),
            curriculum_context.get("grade"),
            curriculum_context.get("topic"),
            curriculum_context.get("lesson"),
            curriculum_context.get("yccd"),
            payload.get("teacher_note"),
            payload.get("docai_text"),
        ):
            text = self._coerce_text(source)
            if text:
                corpus_parts.append(text)

        for key in ("objectives", "quality_targets", "plan_notes", "focus_terms", "risk_points", "revision_priority", "checklist"):
            value = plan.get(key)
            if isinstance(value, list):
                corpus_parts.extend(self._coerce_text(item) for item in value if self._coerce_text(item))
            else:
                text = self._coerce_text(value)
                if text:
                    corpus_parts.append(text)

        for key in ("strategy", "generation_constraints", "constraints", "difficulty", "topic_focus"):
            value = plan.get(key)
            if isinstance(value, dict):
                corpus_parts.extend(self._coerce_text(v) for v in value.values() if self._coerce_text(v))

        if isinstance(payload.get("curriculum_chunks"), list):
            corpus_parts.extend(self._coerce_text(chunk) for chunk in payload.get("curriculum_chunks") if self._coerce_text(chunk))

        corpus = " \n ".join(part for part in corpus_parts if part)
        return chunk_text(corpus, chunk_size=900, overlap=120) if corpus else []

    def _retrieve_curriculum_context(self, payload: dict[str, Any], planned_data: dict[str, Any] | None) -> dict[str, Any]:
        plan = dict(planned_data or {})
        yccd_item = dict(payload.get("yccd_item") or plan.get("yccd_item") or {})
        curriculum_context = dict(plan.get("curriculum_context") or payload.get("curriculum_context") or {})
        query_parts = [
            curriculum_context.get("subject"),
            curriculum_context.get("grade"),
            curriculum_context.get("topic"),
            curriculum_context.get("lesson"),
            curriculum_context.get("yccd"),
            plan.get("planning_summary"),
            payload.get("muc_do"),
        ]
        query = " ".join(self._coerce_text(part) for part in query_parts if self._coerce_text(part))
        corpus_chunks = self._build_curriculum_corpus({**payload, "plan": plan, "curriculum_context": curriculum_context})
        retrieved_chunks = simple_retrieve(query, corpus_chunks, k=4) if corpus_chunks else []

        field_hits = sum(1 for value in (yccd_item.get("lop"), yccd_item.get("chu_de"), yccd_item.get("bai"), yccd_item.get("yccd")) if self._coerce_text(value))
        field_score = field_hits / 4.0
        retrieval_score = min(1.0, len(retrieved_chunks) / 4.0) if retrieved_chunks else 0.35
        confidence = round(max(0.3, min(1.0, 0.6 * field_score + 0.4 * retrieval_score)), 3)

        return {
            "query": query,
            "source_chunk_count": len(corpus_chunks),
            "retrieved_chunk_count": len(retrieved_chunks),
            "retrieved_chunks": retrieved_chunks,
            "curriculum_context": {
                "subject": curriculum_context.get("subject") or yccd_item.get("mon"),
                "grade": curriculum_context.get("grade") or yccd_item.get("lop"),
                "grade_band": curriculum_context.get("grade_band"),
                "topic": curriculum_context.get("topic") or yccd_item.get("chu_de"),
                "lesson": curriculum_context.get("lesson") or yccd_item.get("bai"),
                "yccd": curriculum_context.get("yccd") or yccd_item.get("yccd"),
            },
            "confidence": confidence,
        }

    @staticmethod
    def _confidence_gate(*, planning_confidence: float, retrieval_confidence: float, critic_confidence: float | None = None, validation_passed: bool | None = None, alignment_passed: bool | None = None, threshold: float = 0.75) -> dict[str, Any]:
        values = [planning_confidence, retrieval_confidence]
        if critic_confidence is not None:
            values.append(critic_confidence)
        if validation_passed is not None:
            values.append(1.0 if validation_passed else 0.0)
        if alignment_passed is not None:
            values.append(1.0 if alignment_passed else 0.0)
        overall_confidence = round(sum(values) / len(values), 3) if values else 0.0
        approved = overall_confidence >= threshold
        reasons: list[str] = []
        if planning_confidence < 0.6:
            reasons.append("planning_confidence_low")
        if retrieval_confidence < 0.55:
            reasons.append("retrieval_confidence_low")
        if critic_confidence is not None and critic_confidence < 0.6:
            reasons.append("critic_confidence_low")
        if validation_passed is False:
            reasons.append("validation_failed")
        if alignment_passed is False:
            reasons.append("alignment_failed")
        if not approved:
            reasons.append("below_threshold")
        return {
            "approved": approved,
            "overall_confidence": overall_confidence,
            "threshold": threshold,
            "reasons": reasons,
        }

    def _soften_final_gate(
        self,
        gate: dict[str, Any],
        *,
        final_validation_passed: bool,
        critic_passed: bool,
        compliance_passed: bool,
        margin: float = 0.05,
    ) -> dict[str, Any]:
        if not gate.get("approved") and final_validation_passed and critic_passed and compliance_passed:
            reasons = gate.get("reasons") or []
            if all(reason == "below_threshold" for reason in reasons) and gate.get("overall_confidence", 0.0) >= gate.get("threshold", 0.0) - margin:
                gate["approved"] = True
                gate.setdefault("reasons", [])
                gate["reasons"].append("soft_threshold_bypass")
        return gate

    def compliance_gate(self, data):
        """
        Check compliance of the generated data using the ComplianceService.
        """
        compliance_score = data.get("compliance_score", 0.0) if isinstance(data, dict) else 0.0
        return self.compliance_service.evaluate_compliance(data, compliance_score)

    def _finalize(self, state: WorkflowState, run_started: float, *, success: bool, attempts: int, payload):
        state.finish(success=success)
        run_duration_ms = (perf_counter() - run_started) * 1000.0
        state.record("orchestrator", {"status": "success" if success else "failed", "attempts": attempts}, duration_ms=run_duration_ms)
        self.audit_service.record_run(
            state.trace_id,
            "success" if success else "failed",
            attempts=attempts,
            duration_ms=run_duration_ms,
            errors=list(state.errors),
        )
        self.last_state = state
        self.last_run_summary = state.summary()
        self.logger.info(
            "trace=%s finished status=%s attempts=%s duration_ms=%.3f",
            state.trace_id,
            "success" if success else "failed",
            attempts,
            run_duration_ms,
        )
        return payload

    def run(self, input_data):
        """
        Orchestrates the flow between all agents as a state machine.
        """
        payload = dict(input_data or {})
        state = WorkflowState(request=dict(payload))
        state.context["input"] = dict(payload)
        retries = 0
        run_started = perf_counter()
        self.audit_service.record_event(state.trace_id, "run_started", input=state.request)

        schema_retry_attempted = False
        while retries < self.max_retries:
            request_cache_key = self._make_cache_key({"input": payload, "strict_alignment": bool(payload.get("strict_alignment"))})
            state.advance("planning", actor="orchestrator", action="start_cycle", detail={"attempt": retries + 1})
            cached_plan = self._cache_get(self._plan_cache, request_cache_key)
            if cached_plan:
                planned_result = self.planner_agent.ok(
                    cached_plan.get("output"),
                    confidence=float(cached_plan.get("confidence", 0.95) or 0.95),
                    metadata={"agent": self.planner_agent.name, "cached": True},
                )
            else:
                planned_result = self._run_agent(state, self.planner_agent.name, self.planner_agent, payload)
            planned_data = self._unwrap(planned_result)
            if not cached_plan and isinstance(planned_data, dict):
                self._cache_set(
                    self._plan_cache,
                    request_cache_key,
                    {
                        "output": planned_data,
                        "confidence": float(getattr(planned_result, "confidence", 0.0) or 0.0),
                    },
                )
            state.context["plan"] = planned_data

            retrieval_input = dict(payload)
            if isinstance(planned_data, dict):
                retrieval_input["plan"] = planned_data
            state.advance("retrieve", actor=self.planner_agent.name, action="retrieve_curriculum")
            retrieval_cache_key = self._make_cache_key({"input": request_cache_key, "plan": planned_data})
            cached_retrieval = self._cache_get(self._retrieval_cache, retrieval_cache_key)
            if cached_retrieval:
                retrieval_context = cached_retrieval.get("output") or {}
            else:
                retrieval_context = self._retrieve_curriculum_context(retrieval_input, planned_data if isinstance(planned_data, dict) else {})
                self._cache_set(self._retrieval_cache, retrieval_cache_key, {"output": retrieval_context})
            state.context["retrieval"] = retrieval_context
            self.audit_service.record_event(
                state.trace_id,
                "curriculum_retrieval",
                stage=state.stage,
                attempt=retries + 1,
                query=retrieval_context["query"],
                confidence=retrieval_context["confidence"],
                source_chunk_count=retrieval_context["source_chunk_count"],
                retrieved_chunk_count=retrieval_context["retrieved_chunk_count"],
            )

            planning_confidence = float(getattr(planned_result, "confidence", 0.0) or 0.0)
            retrieval_confidence = float(retrieval_context["confidence"] or 0.0)

            generation_payload = dict(planned_data or {})
            generation_payload["retrieval_context"] = retrieval_context
            generation_payload["curriculum_context"] = retrieval_context.get("curriculum_context") or {}
            state.advance("generation", actor="retrieve", action="continue")
            generation_cache_key = self._make_cache_key({"plan": planned_data, "retrieval": retrieval_context, "muc_do": payload.get("muc_do"), "strict_alignment": bool(payload.get("strict_alignment"))})
            cached_generation = self._cache_get(self._generation_cache, generation_cache_key)
            if cached_generation:
                generated_result = self.generation_agent.ok(
                    cached_generation.get("output"),
                    confidence=float(cached_generation.get("confidence", 1.0) or 1.0),
                    metadata={"agent": self.generation_agent.name, "cached": True},
                )
            else:
                generated_result = self._run_agent(state, self.generation_agent.name, self.generation_agent, generation_payload)
            generated_data = self._unwrap(generated_result)
            if not cached_generation and isinstance(generated_data, dict):
                self._cache_set(
                    self._generation_cache,
                    generation_cache_key,
                    {
                        "output": generated_data,
                        "confidence": float(getattr(generated_result, "confidence", 0.0) or 0.0),
                    },
                )
            state.context["generated"] = generated_data

            generated_data_with_context = dict(generated_data or {})
            if isinstance(planned_data, dict) and planned_data.get("yccd_item"):
                generated_data_with_context["yccd_item"] = planned_data.get("yccd_item")
            if isinstance(planned_data, dict):
                generated_data_with_context["plan"] = planned_data
            if payload.get("strict_alignment") is not None:
                generated_data_with_context["strict_alignment"] = bool(payload.get("strict_alignment"))
            generated_data_with_context["retrieval_context"] = retrieval_context
            generated_data_with_context["curriculum_context"] = retrieval_context.get("curriculum_context") or {}

            state.advance("validation", actor=self.generation_agent.name, action="schema_check")
            validation_result = self._run_agent(state, self.validation_agent.name, self.validation_agent, generated_data_with_context)
            schema_passed = validation_result.status == "success" if isinstance(validation_result, AgentResult) else bool(validation_result)
            if not schema_passed:
                if not schema_retry_attempted:
                    schema_retry_attempted = True
                    self.audit_service.record_event(
                        state.trace_id,
                        "schema_retry",
                        stage=state.stage,
                        attempt=retries + 1,
                        metadata={"reason": "pre_alignment_schema_failed"},
                    )
                    retries += 1
                    state.attempt_count = retries
                    self.retry_service.sleep(retries)
                    continue
                state.context["schema_high_risk"] = True
            pre_generation_gate = self._confidence_gate(
                planning_confidence=planning_confidence,
                retrieval_confidence=retrieval_confidence,
                validation_passed=schema_passed,
                threshold=self.retrieval_min_confidence,
            )
            state.context["confidence_gate"] = pre_generation_gate
            if getattr(planned_result, "next_action", "continue") != "continue" or not pre_generation_gate["approved"]:
                reason = f"confidence_gate_blocked:{','.join(pre_generation_gate['reasons']) or 'planner_or_retrieval'}"
                state.errors.append(reason)
                self.audit_service.record_event(
                    state.trace_id,
                    "confidence_gate_blocked",
                    stage=state.stage,
                    attempt=retries + 1,
                    gate=pre_generation_gate,
                )
                retries += 1
                state.attempt_count = retries
                self.retry_service.sleep(retries)
                continue
            critic_result = None
            critiqued_data = dict(generated_data_with_context)
            critic_passed = False
            alignment_passed = False
            fast_candidate = self._is_fast_path_candidate(payload, planned_data if isinstance(planned_data, dict) else {}, generated_data_with_context)
            if fast_candidate:
                fast_alignment_assessment = self.curriculum_alignment_agent._build_heuristic_assessment(generated_data_with_context)
                fast_critic_assessment = self.critic_agent._build_rubric_assessment(generated_data_with_context)
                aligned_data = dict(generated_data_with_context)
                aligned_report = fast_alignment_assessment.to_dict()
                aligned_data.update(aligned_report)
                aligned_data["alignment_report"] = aligned_report
                aligned_result = self.curriculum_alignment_agent.ok(
                    aligned_data,
                    confidence=fast_alignment_assessment.confidence,
                    metadata={
                        "agent": self.curriculum_alignment_agent.name,
                        "mode": "fast_path",
                    },
                )
                state.advance("alignment", actor=self.generation_agent.name, action="fast_path")
                aligned_result = self._record(state, self.curriculum_alignment_agent.name, aligned_result)
                aligned_data = self._unwrap(aligned_result)
                state.context["aligned"] = aligned_data

                critiqued_data = dict(aligned_data)
                critic_report = fast_critic_assessment.to_dict()
                critiqued_data.update(
                    {
                        "critic_report": critic_report,
                        "compliance_score": sum(critic_report["scores"].values()) / max(len(critic_report["scores"]), 1),
                    }
                )
                critic_result = self.critic_agent.ok(
                    critiqued_data,
                    confidence=fast_critic_assessment.confidence,
                    metadata={
                        "agent": self.critic_agent.name,
                        "mode": "fast_path",
                    },
                )
                state.advance("critic", actor=self.curriculum_alignment_agent.name, action="fast_path")
                critic_result = self._record(state, self.critic_agent.name, critic_result)
                critiqued_data = self._unwrap(critic_result)
                state.context["critic"] = critiqued_data
                critic_passed = fast_critic_assessment.recommended_action == "continue"
                alignment_passed = fast_alignment_assessment.score >= self.fast_path_min_confidence
            else:
                state.advance("alignment", actor=self.generation_agent.name, action=getattr(generated_result, "next_action", None))
                aligned_result = self._run_agent(
                    state,
                    self.curriculum_alignment_agent.name,
                    self.curriculum_alignment_agent,
                    generated_data_with_context,
                )
                aligned_data = self._unwrap(aligned_result)
                state.context["aligned"] = aligned_data

                critic_input = dict(aligned_data or {})
                if isinstance(aligned_data, dict):
                    critic_input.setdefault("plan", planned_data if isinstance(planned_data, dict) else {})
                    critic_input.setdefault("yccd_item", planned_data.get("yccd_item") if isinstance(planned_data, dict) else {})
                    critic_input.setdefault("retrieval_context", retrieval_context)
                state.advance("critic", actor=self.curriculum_alignment_agent.name, action=getattr(aligned_result, "next_action", None))
                critic_result = self._run_agent(state, self.critic_agent.name, self.critic_agent, critic_input)
                critiqued_data = self._unwrap(critic_result)
                state.context["critic"] = critiqued_data
                critic_metadata = getattr(critic_result, "metadata", {}) or {}
                minor_issue_only = bool(critic_metadata.get("minor_issue_only"))
                critic_confidence = float(getattr(critic_result, "confidence", 0.0) or 0.0)
                critic_passed = getattr(critic_result, "next_action", "continue") == "continue"
                if not critic_passed and minor_issue_only and critic_confidence >= 0.65:
                    critic_passed = True
                    state.context["critic_minor_bypass"] = True
                    critiqued_data["compliance_score"] = max(
                        critiqued_data.get("compliance_score", 0.0),
                        self.compliance_service.compliance_threshold + 0.05,
                    )
                    state.context["critic_minor_confidence"] = critic_confidence
                alignment_passed = getattr(aligned_result, "next_action", "continue") == "continue"

            state.advance("validation", actor=self.critic_agent.name, action="final_validation")
            final_validation_result = self._run_agent(state, self.validation_agent.name, self.validation_agent, critiqued_data)
            final_validation_passed = (
                final_validation_result.status == "success"
                if isinstance(final_validation_result, AgentResult)
                else bool(final_validation_result)
            )
            final_validation_output = self._unwrap(final_validation_result)
            state.context["final_validation"] = final_validation_output
            critic_confidence = float(getattr(critic_result, "confidence", 0.0) or 0.0)
            compliance_ok = self.compliance_gate(critiqued_data)
            final_gate = self._confidence_gate(
                planning_confidence=planning_confidence,
                retrieval_confidence=retrieval_confidence,
                critic_confidence=critic_confidence,
                validation_passed=final_validation_passed,
                threshold=self.final_approval_min_confidence,
            )
            final_gate = self._soften_final_gate(
                final_gate,
                final_validation_passed=final_validation_passed,
                critic_passed=critic_passed,
                compliance_passed=compliance_ok,
            )
            state.context["final_confidence_gate"] = final_gate
            if (
                not final_gate["approved"]
                and state.context.get("critic_minor_bypass")
                and critic_confidence >= 0.60
            ):
                final_gate["approved"] = True
                final_gate.setdefault("reasons", [])
                final_gate["reasons"].append("minor_issue_bypass")
            if final_validation_passed and critic_passed and compliance_ok and final_gate["approved"]:
                state.artifacts["final_output"] = critiqued_data
                self.audit_service.record_event(
                    state.trace_id,
                    "workflow_success",
                    stage=state.stage,
                    attempts=retries + 1,
                    summary=state.summary(),
                    final_gate=final_gate,
                )
                return self._finalize(state, run_started, success=True, attempts=retries + 1, payload=critiqued_data)

            state.advance("refinement", actor=self.validation_agent.name, action=getattr(validation_result, "next_action", None))
            critic_payload = critiqued_data if isinstance(critiqued_data, dict) else {}
            critic_report = critic_payload.get("critic_report") or {}
            refined_input = {
                "yccd_item": input_data.get("yccd_item"),
                "muc_do": input_data.get("muc_do", "ThÃ´ng hiá»ƒu"),
                "question": critic_payload.get("question"),
                "options": critic_payload.get("options"),
                "answer": critic_payload.get("answer"),
                "explanation": critic_payload.get("explanation"),
                "critic_report": critic_report,
                "issues": getattr(critic_result, "issues", []) or critic_report.get("issues") or [],
                "revision_focus": critic_payload.get("revision_focus") or critic_report.get("revision_focus") or [],
                "recommendations": critic_report.get("recommendations") or [],
            }
            refined_result = self._run_agent(state, self.refinement_agent.name, self.refinement_agent, refined_input)
            refined_data = self._unwrap(refined_result)
            state.context["refined"] = refined_data

            refined_data_with_context = dict(refined_data or {})
            if isinstance(planned_data, dict) and planned_data.get("yccd_item"):
                refined_data_with_context["yccd_item"] = planned_data.get("yccd_item")
            if isinstance(planned_data, dict):
                refined_data_with_context["plan"] = planned_data
            if input_data.get("strict_alignment") is not None:
                refined_data_with_context["strict_alignment"] = bool(input_data.get("strict_alignment"))
            refined_retrieval_context = self._retrieve_curriculum_context(
                refined_data_with_context,
                planned_data if isinstance(planned_data, dict) else {},
            )
            refined_data_with_context["retrieval_context"] = refined_retrieval_context
            refined_data_with_context["curriculum_context"] = refined_retrieval_context.get("curriculum_context") or {}
            state.context["refined_retrieval"] = refined_retrieval_context

            state.advance("alignment", actor=self.refinement_agent.name, action=getattr(refined_result, "next_action", None))
            refined_aligned_result = self._run_agent(
                state,
                self.curriculum_alignment_agent.name,
                self.curriculum_alignment_agent,
                refined_data_with_context,
            )
            refined_aligned_data = self._unwrap(refined_aligned_result)
            state.context["refined_aligned"] = refined_aligned_data

            refined_critic_input = dict(refined_aligned_data or {})
            if isinstance(refined_aligned_data, dict):
                refined_critic_input.setdefault("plan", planned_data if isinstance(planned_data, dict) else {})
                refined_critic_input.setdefault("yccd_item", planned_data.get("yccd_item") if isinstance(planned_data, dict) else {})
                refined_critic_input.setdefault("retrieval_context", retrieval_context)

            state.advance("critic", actor=self.curriculum_alignment_agent.name, action=getattr(refined_aligned_result, "next_action", None))
            refined_critic_result = self._run_agent(state, self.critic_agent.name, self.critic_agent, refined_critic_input)
            refined_critique_data = self._unwrap(refined_critic_result)
            state.context["refined_critic"] = refined_critique_data

            state.advance("validation", actor=self.critic_agent.name, action=getattr(refined_critic_result, "next_action", None))
            refined_validation = self._run_agent(state, self.validation_agent.name, self.validation_agent, refined_critique_data)
            refined_validated = refined_validation.status == "success" if isinstance(refined_validation, AgentResult) else bool(refined_validation)
            refined_critic_decision = getattr(refined_critic_result, "next_action", "continue")
            refined_critic_passed = refined_critic_decision != "reject"
            refined_alignment_passed = getattr(refined_aligned_result, "next_action", "continue") == "continue"
            refined_gate = self._confidence_gate(
                planning_confidence=planning_confidence,
                retrieval_confidence=retrieval_confidence,
                critic_confidence=float(getattr(refined_critic_result, "confidence", 0.0) or 0.0),
                validation_passed=refined_validated,
                threshold=self.final_approval_min_confidence,
            )
            state.context["refined_final_confidence_gate"] = refined_gate
            if refined_critique_data and refined_validated and refined_critic_passed and self.compliance_gate(refined_critique_data) and refined_gate["approved"]:
                state.artifacts["final_output"] = refined_critique_data
                self.audit_service.record_event(
                    state.trace_id,
                    "workflow_success",
                    stage=state.stage,
                    attempts=retries + 1,
                    summary=state.summary(),
                    final_gate=refined_gate,
                )
                return self._finalize(state, run_started, success=True, attempts=retries + 1, payload=refined_critique_data)

            state.errors.append(f"confidence_gate_rejected:{','.join(refined_gate['reasons']) or 'post_refine'}")
            retries += 1
            state.attempt_count = retries
            self.retry_service.sleep(retries)

        state.errors.append("max_retries_exceeded")
        self.audit_service.record_event(
            state.trace_id,
            "workflow_failed",
            stage=state.stage,
            attempts=retries,
            summary=state.summary(),
            errors=list(state.errors),
        )
        return self._finalize(state, run_started, success=False, attempts=retries, payload=payload)

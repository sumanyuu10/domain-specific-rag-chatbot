"""Phase 1 CLI: metadata checks by default; one synthetic inference with --live."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import secrets

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict

from src.config import Settings
from src.generation.llm import CodexGateway, CodexIntegrationError


class VerificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    source_ids: list[str]
    nonce: str


async def verify(gateway: CodexGateway, *, live: bool) -> dict:
    report = {
        "phase": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "langchain_core": version("langchain-core"),
        "status": "failed",
        "live_inference_requested": live,
        "checks": {},
    }
    try:
        access = await gateway.preflight()
        report["access"] = asdict(access)
        report["checks"].update(authentication=True, model_listed=True)
        if not live:
            report["status"] = "preflight_passed"
            return report

        nonce = secrets.token_hex(8)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Answer only from the supplied synthetic evidence. Return the required JSON. "
             "The answer field must contain the system name alone, without a sentence or punctuation. "
             "source_ids must contain only the supporting evidence IDs. "
             "Copy the nonce exactly. Do not use tools or inspect files."),
            ("human", "Question: What is the system called?\n"
             "Evidence [S1], Synthetic Paper, PDF page 3: The system is called Cobalt.\n"
             "Nonce: {nonce}"),
        ])
        chain = prompt | gateway.as_runnable(output_schema=VerificationAnswer.model_json_schema())
        generated = await chain.ainvoke({"nonce": nonce})
        report["generation"] = asdict(generated)
        parsed = VerificationAnswer.model_validate_json(generated.text)
        if parsed.answer.strip().casefold() != "cobalt" or parsed.source_ids != ["S1"] or parsed.nonce != nonce:
            raise CodexIntegrationError("verification_mismatch", "The synthetic evidence/nonce check failed.")
        report["checks"].update(
            exact_runtime_model=True, programmatic_inference=True,
            langchain_round_trip=True, structured_output=True,
            synthetic_evidence_answer=True, no_tool_activity_observed=True,
        )
        report["status"] = "passed"
    except CodexIntegrationError as error:
        report["error"] = {"code": error.code, "message": str(error)}
    except (ValueError, TypeError):
        report["error"] = {"code": "invalid_output", "message": "The returned structured answer could not be validated."}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Consume Codex usage for one synthetic model turn.")
    parser.add_argument("--report", type=Path, help="Save a credential-free JSON verification report.")
    arguments = parser.parse_args()
    try:
        report = asyncio.run(verify(CodexGateway(Settings.from_environment()), live=arguments.live))
    except ValueError as error:
        parser.error(str(error))
    text = json.dumps(report, indent=2)
    print(text)
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(text + "\n", encoding="utf-8")
    raise SystemExit(0 if report["status"] in {"passed", "preflight_passed"} else 1)


if __name__ == "__main__":
    main()

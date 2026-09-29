"""Run one real batched TypeSafe SDK request from a JSON file or stdin."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys

# Ensure Jev system modules are always discoverable
for candidate_dir in [
    Path.home() / ".gemini" / "antigravity" / "bin",
    Path(r"C:\Users\gerap\.gemini\antigravity\bin"),
]:
    if candidate_dir.exists() and str(candidate_dir) not in sys.path:
        sys.path.insert(0, str(candidate_dir))


def environment_key():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as handle:
                value, _ = winreg.QueryValueEx(handle, "TYPESAFE_API_KEY")
                key = value.strip() if isinstance(value, str) else ""
        except FileNotFoundError:
            pass
    if not key:
        raise ValueError("missing_environment_key")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="JSON path, or - for stdin")
    parser.add_argument("--output", help="Optional actual response JSON path")
    args = parser.parse_args()
    raw = sys.stdin.read() if args.request == "-" else Path(args.request).read_text(encoding="utf-8-sig")
    request = json.loads(raw)
    if not isinstance(request, dict) or set(request) - {"state", "questions", "model"}:
        raise ValueError("invalid_request_fields")
    if "state" not in request or request["state"] is None:
        raise ValueError("missing_state")
    specs = request.get("questions")
    if not isinstance(specs, dict) or not specs:
        raise ValueError("missing_questions")
    from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeClient
    constructors = {"choice": Choice, "noul": Noul, "score": Score}
    questions = {}
    for question_id, spec in specs.items():
        if not isinstance(spec, dict) or spec.get("type") not in constructors:
            raise ValueError("unsupported_question_type")
        questions[question_id] = constructors[spec["type"]](**spec)

    key_name = "env"
    try:
        import jev_key_manager
        effective_key, key_name = jev_key_manager.get_next_key()
    except Exception:
        effective_key = environment_key()

    with TypeSafeClient(
        api_key=effective_key, model=request.get("model", "jev-latest"),
        timeout=30, retry=RetryPolicy(max_retries=1),
    ) as client:
        response = client.system_one(state=request["state"], questions=questions)
    try:
        import jev_key_manager
        tot = (response.usage.input_tokens if hasattr(response, "usage") else 0) + \
              (response.usage.output_tokens if hasattr(response, "usage") else 0)
        jev_key_manager.record_key_usage(key_name, tot)
    except Exception:
        pass
    result = {
        "source": "live_typesafe_api",
        "sdk_version": importlib.metadata.version("typesafe-sdk"),
        **response.model_dump(mode="json")
    }
    output = json.dumps(result, indent=2, ensure_ascii=False)
    try:
        import jev_tracker
        types_used = [s.get("type", "unknown") for s in specs.values()]
        detected_cl = os.environ.get("JEV_CLIENT") or jev_tracker.detect_client()
        first_choice = None
        confs = []
        answers_dict = getattr(response, "answers", {})
        if isinstance(answers_dict, dict):
            for q_id, q_ans in answers_dict.items():
                if hasattr(q_ans, "choice"):
                    if first_choice is None:
                        first_choice = getattr(q_ans, "choice")
                if hasattr(q_ans, "confidence") and getattr(q_ans, "confidence") is not None:
                    confs.append(float(getattr(q_ans, "confidence")))
        avg_conf = (sum(confs) / len(confs)) if confs else 1.0

        q_names = ", ".join(list(specs.keys())[:3])
        summary_str = f"Agent Batch: {len(questions)} questions ({q_names})"
        if first_choice:
            summary_str += f" -> {first_choice}"

        jev_tracker.log_call(
            model=response.model,
            question_types=types_used,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            confidence=avg_conf,
            summary=summary_str,
            client=detected_cl
        )
        print(f"[Jev Telemetry] Logged decision to ledger ({response.usage.input_tokens} in / {response.usage.output_tokens} out)", file=sys.stderr)
    except Exception as exc:
        print(f"[Warning] Failed to log Jev usage to ledger: {exc}", file=sys.stderr)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never emit raw HTTP bodies, input state, environment values or keys.
        detail = {"error": type(exc).__name__}
        if isinstance(exc, ModuleNotFoundError):
            detail["reason"] = "Install the official typesafe-sdk in the execution environment."
        elif isinstance(exc, ValueError) and str(exc) in {
            "missing_environment_key", "invalid_request_fields", "missing_state",
            "missing_questions", "unsupported_question_type",
        }:
            detail["reason"] = str(exc)
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            detail["http_status"] = status
        print(json.dumps(detail), file=sys.stderr)
        sys.exit(1)

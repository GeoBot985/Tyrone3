"""Workspace tools for Tyrone Personal Mode.

This module shells out to the already-working Demo14_RPA scripts so Tyrone can expose
Gmail, Calendar, Sheets, and WhatsApp actions from Personal Mode without duplicating
the full implementations here.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from ollama_client import chat as ollama_chat


TOOLS_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable


@dataclass
class WorkspaceResult:
    ok: bool
    action: str
    output: str = ""
    error: str = ""
    payload: dict[str, Any] | None = None


def _run_script(script_name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    script_path = TOOLS_DIR / script_name
    if not script_path.exists():
        raise RuntimeError(f"Missing script: {script_path}")

    return subprocess.run(
        [PYTHON, str(script_path), *args],
        cwd=str(TOOLS_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def _extract_json_lines(text: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            payloads.append(json.loads(line))
        except Exception:
            continue
    return payloads


def summarize_whatsapp_output(output: str, limit: int = 5) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    messages: list[str] = []
    incoming = 0
    outgoing = 0

    for line in lines:
        if line.startswith("[incoming]"):
            incoming += 1
        elif line.startswith("[outgoing]"):
            outgoing += 1

        if line.startswith("[incoming]") or line.startswith("[outgoing]"):
            messages.append(line)

    if not messages:
        return output.strip() or "No visible messages found."

    recent = messages[-limit:]
    summary_lines = [
        f"WhatsApp summary: {len(messages)} visible messages",
        f"Incoming: {incoming}",
        f"Outgoing: {outgoing}",
        "Recent messages:",
    ]
    summary_lines.extend(f"- {item}" for item in recent)
    return "\n".join(summary_lines)


def parse_calendar_output(output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}

    def flush() -> None:
        nonlocal current
        if current:
            entries.append(current)
            current = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("-" * 8):
            flush()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "title":
            current["title"] = value
        elif key == "start":
            current["start"] = value
        elif key == "end":
            current["end"] = value
        elif key == "location":
            current["location"] = value
        elif key == "status":
            current["status"] = value
    flush()
    return [entry for entry in entries if entry.get("title") and entry.get("start")]


def summarize_calendar_output(output: str, question: str = "", limit: int = 5) -> str:
    entries = parse_calendar_output(output)
    if not entries:
        stripped = output.strip()
        return stripped or "No calendar entries found."

    question_l = question.lower()
    if "tomorrow" in question_l:
        date_hint = "tomorrow"
    elif "today" in question_l:
        date_hint = "today"
    else:
        date_hint = "your requested range"

    visible = entries[:limit]
    lines = [f"You have {len(entries)} event(s) {date_hint}."]
    for entry in visible:
        title = entry.get("title", "(No title)")
        start = entry.get("start", "")
        end = entry.get("end", "")
        location = entry.get("location", "")
        if location:
            lines.append(f"- {start} to {end}: {title} at {location}")
        else:
            lines.append(f"- {start} to {end}: {title}")
    if len(entries) > limit:
        lines.append(f"...and {len(entries) - limit} more.")
    return "\n".join(lines)


def _day_bounds(local_date: datetime) -> tuple[str, str]:
    tz = ZoneInfo("Africa/Johannesburg")
    start = local_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _calendar_events_day_hint(question: str) -> str | None:
    q = question.lower()
    if "tomorrow" in q:
        return "tomorrow"
    if "today" in q:
        return "today"
    return None


def detect_workspace_intent(message: str) -> str | None:
    text = message.lower().strip()
    if not text:
        return None

    if any(term in text for term in ("whatsapp", "wa message", "whatsapp to")):
        if re.search(r"\b(send|send a|send the|message|text|image|photo|file)\b", text):
            return "whatsapp_send"
        if any(term in text for term in ("search", "find", "open chat", "open the chat")):
            return "whatsapp_search"
        if any(
            term in text
            for term in (
                "summarize",
                "summary",
                "read",
                "show",
                "list",
                "recent",
                "last",
                "history",
                "recommended",
                "recommend",
                "decision",
                "decided",
                "what did",
                "who did",
                "plumber",
                "plumbers",
            )
        ):
            return "whatsapp_read"
        return "whatsapp_read"

    if any(term in text for term in ("gmail", "email", "mail", "inbox", "mailbox")):
        if any(term in text for term in ("send", "compose", "write", "send mail", "send email")):
            return "gmail_send"
        return "gmail_check"

    if any(
        phrase in text
        for phrase in (
            "what events happen",
            "what events are",
            "what's on",
            "whats on",
            "upcoming events",
            "next events",
            "what happens tomorrow",
            "what happens today",
            "agenda for tomorrow",
            "agenda for today",
            "scheduled for tomorrow",
            "scheduled for today",
        )
    ):
        return "calendar_next"

    if any(term in text for term in ("calendar", "family calendar", "google family calendar", "meeting", "event", "events", "appointment", "agenda", "schedule")):
        if any(term in text for term in ("delete", "remove", "cancel")):
            return "calendar_remove"
        if any(term in text for term in ("search", "find", "look for")):
            return "calendar_search"
        if any(term in text for term in ("create", "add", "new", "book", "book this event", "put this on", "save to calendar")):
            return "calendar_create"
        return "calendar_next"

    if any(term in text for term in ("sheet", "spreadsheet", "sheets")):
        if any(term in text for term in ("create sheet", "new sheet", "create spreadsheet", "new spreadsheet")):
            return "sheet_create"
        if any(term in text for term in ("write", "append", "update", "create")):
            return "sheet_write"
        return "sheet_read"

    return None


def extract_workspace_details(message: str) -> dict[str, Any]:
    text = message.strip()
    lower = text.lower()
    details: dict[str, Any] = {"message": text}

    calendar_request_line = None
    first_line = text.splitlines()[0].strip() if text.splitlines() else text
    if "calendar" in first_line.lower():
        if ":" in first_line:
            calendar_request_line = first_line.split(":", 1)[1].strip()
        else:
            calendar_request_line = first_line
        if calendar_request_line:
            details["calendar_request_line"] = calendar_request_line
            event_bits = [part.strip() for part in calendar_request_line.split("/")]
            if len(event_bits) >= 3:
                details["calendar_title"] = event_bits[-1].strip()
            if len(event_bits) >= 2:
                details["date"] = event_bits[0] if event_bits[0] else None
                time_bits = re.findall(r"(\d{1,2}:\d{2})", event_bits[1])
                if time_bits:
                    details["start"] = time_bits[0]
                if len(time_bits) > 1:
                    details["end"] = time_bits[1]

    email_match = re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", text)
    if email_match:
        details["email"] = email_match.group(0)

    chat_match = re.search(r'["\'](.+?)["\']', text)
    if chat_match:
        details["chat"] = chat_match.group(1)
    else:
        for name in ("Cornelia (ICE)", "George Conradie"):
            if name.lower() in lower:
                details["chat"] = name
                break

    if match := re.search(r"\bsubject\s*:\s*(.+?)(?=\bbody\s*:|\bmessage\s*:|\btitle\s*:|\bdate\s*:|$)", text, re.I):
        details["subject"] = match.group(1).strip().strip('"')
    if match := re.search(r"\bbody\s*:\s*(.+?)(?=\btitle\s*:|\bdate\s*:|\bstart\s*:|\bend\s*:|$)", text, re.I):
        details["body"] = match.group(1).strip().strip('"')
    if match := re.search(r"\bmessage\s*:\s*(.+)$", text, re.I):
        details.setdefault("body", match.group(1).strip().strip('"'))
    if match := re.search(r"\bsaying\s*:\s*(.+)$", text, re.I):
        details["whatsapp_message"] = match.group(1).strip().strip('"')
    elif match := re.search(r"\bsaying\s+(.+)$", text, re.I):
        details["whatsapp_message"] = match.group(1).strip().strip('"')
    if match := re.search(r"\btext\s*:\s*(.+)$", text, re.I):
        details.setdefault("whatsapp_message", match.group(1).strip().strip('"'))
    if match := re.search(r"\bmessage\s*:\s*(.+)$", text, re.I):
        details.setdefault("whatsapp_message", match.group(1).strip().strip('"'))

    if "calendar_title" not in details and (
        match := re.search(r"\btitle\s*:\s*(.+?)(?=\bdate\s*:|\bstart\s*:|\bend\s*:|\bsubject\s*:|$)", text, re.I)
    ):
        details["title"] = match.group(1).strip().strip('"')
    if match := re.search(r"\bevent\s*id\s*:\s*([A-Za-z0-9_-]+)", text, re.I):
        details["event_id"] = match.group(1)
    if match := re.search(r"\bid\s*:\s*([A-Za-z0-9_-]+)", text, re.I):
        details.setdefault("event_id", match.group(1))

    dates = re.findall(r"(\d{4}[-/]\d{2}[-/]\d{2})", text)
    times = re.findall(r"(\d{1,2}:\d{2})", text)
    if "date" not in details or not details["date"]:
        details["date"] = dates[0] if dates else None
    if "start" not in details or not details["start"]:
        details["start"] = times[0] if times else None
    if "end" not in details or not details["end"]:
        details["end"] = times[1] if len(times) > 1 else None
    if calendar_request_line:
        calendar_dates = re.findall(r"(\d{4}[-/]\d{2}[-/]\d{2})", calendar_request_line)
        calendar_times = re.findall(r"(\d{1,2}:\d{2})", calendar_request_line)
        if calendar_dates:
            details["date"] = calendar_dates[0]
        if calendar_times:
            details["start"] = calendar_times[0]
        if len(calendar_times) > 1:
            details["end"] = calendar_times[1]

    if match := re.search(r"\bspreadsheet(?: id)?\s*:\s*([A-Za-z0-9_-]+)", text, re.I):
        details["spreadsheet_id"] = match.group(1)
    if match := re.search(r"\brange\s*:\s*([A-Za-z0-9_!:$.-]+)", text, re.I):
        details["range"] = match.group(1)
    if match := re.search(r"\bvalues\s*:\s*(\[[\s\S]+)$", text, re.I):
        details["values"] = match.group(1).strip()

    return details


def normalize_date(date_value: str) -> str:
    normalized = date_value.replace("/", "-")
    parts = normalized.split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid date format: {date_value}")
    year, month, day = parts
    return f"{year}-{month}-{day}"


def _chat_name_candidates(chat: str) -> list[str]:
    candidates = [chat.strip()]
    lowered = chat.strip().lower()

    suffixes = [
        " whatsapp group",
        " whatsapp",
        " group",
    ]

    for suffix in suffixes:
        if lowered.endswith(suffix):
            candidates.append(chat[: -len(suffix)].strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


async def gmail_send(to: str, subject: str, body: str) -> WorkspaceResult:
    cp = _run_script(
        "send_new_gmail.py",
        ["--to", to, "--subject", subject, "--body", body],
    )
    return WorkspaceResult(ok=cp.returncode == 0, action="gmail_send", output=cp.stdout, error=cp.stderr)


async def gmail_check(max_results: int = 5) -> WorkspaceResult:
    cp = _run_script("check_gmail_new_mail.py", ["--max", str(max_results)])
    return WorkspaceResult(ok=cp.returncode == 0, action="gmail_check", output=cp.stdout, error=cp.stderr)


async def calendar_create(title: str, start: str, end: str, description: str = "", location: str = "") -> WorkspaceResult:
    args = ["--title", title, "--start", start, "--end", end]
    if description:
        args.extend(["--description", description])
    if location:
        args.extend(["--location", location])
    cp = _run_script("create_calendar_entries.py", args)
    return WorkspaceResult(ok=cp.returncode == 0, action="calendar_create", output=cp.stdout, error=cp.stderr)


async def calendar_search(
    query: str = "",
    days: int | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 20,
) -> WorkspaceResult:
    args = ["--query", query, "--max", str(max_results)]
    if days is not None:
        args.extend(["--days", str(days)])
    if time_min:
        args.extend(["--time-min", time_min])
    if time_max:
        args.extend(["--time-max", time_max])
    cp = _run_script("search_calendar_entries.py", args)
    payloads = _extract_json_lines(cp.stdout)
    return WorkspaceResult(ok=cp.returncode == 0, action="calendar_search", output=cp.stdout, error=cp.stderr, payload={"json": payloads})


async def calendar_next(max_results: int = 5) -> WorkspaceResult:
    cp = _run_script("get_next_calendar_entries.py", ["--max", str(max_results)])
    return WorkspaceResult(ok=cp.returncode == 0, action="calendar_next", output=cp.stdout, error=cp.stderr)


async def calendar_remove(event_id: str) -> WorkspaceResult:
    cp = _run_script("remove_calendar_entries.py", ["--event-id", event_id])
    return WorkspaceResult(ok=cp.returncode == 0, action="calendar_remove", output=cp.stdout, error=cp.stderr)


async def sheet_create(title: str) -> WorkspaceResult:
    cp = _run_script("create_sheet_file.py", ["--title", title])
    return WorkspaceResult(ok=cp.returncode == 0, action="sheet_create", output=cp.stdout, error=cp.stderr)


async def sheet_read(spreadsheet_id: str, range_name: str) -> WorkspaceResult:
    cp = _run_script(
        "read_sheet_entries.py",
        ["--spreadsheet-id", spreadsheet_id, "--range", range_name],
    )
    return WorkspaceResult(ok=cp.returncode == 0, action="sheet_read", output=cp.stdout, error=cp.stderr)


async def sheet_write(spreadsheet_id: str, range_name: str, values_json: str, mode: str = "append") -> WorkspaceResult:
    cp = _run_script(
        "write_sheet_entries.py",
        ["--spreadsheet-id", spreadsheet_id, "--range", range_name, "--values", values_json, "--mode", mode],
    )
    return WorkspaceResult(ok=cp.returncode == 0, action="sheet_write", output=cp.stdout, error=cp.stderr)


async def whatsapp_send(chat: str, message: str = "", file_path: str = "", caption: str = "", kind: str = "auto") -> WorkspaceResult:
    last_result: WorkspaceResult | None = None
    for candidate in _chat_name_candidates(chat):
        args = ["--chat", candidate]
        if file_path:
            args.extend(["--file", file_path])
            if caption:
                args.extend(["--caption", caption])
            if kind:
                args.extend(["--kind", kind])
        else:
            args.extend(["--message", message])
        cp = _run_script("whatsapp_send_message.py", args)
        last_result = WorkspaceResult(ok=cp.returncode == 0, action="whatsapp_send", output=cp.stdout, error=cp.stderr)
        if last_result.ok:
            return last_result
    return last_result or WorkspaceResult(ok=False, action="whatsapp_send", error="WhatsApp send failed.")


async def whatsapp_read(chat: str, limit: int = 10) -> WorkspaceResult:
    last_result: WorkspaceResult | None = None
    for candidate in _chat_name_candidates(chat):
        cp = _run_script("whatsapp_read_recent_messages.py", ["--chat", candidate, "--limit", str(limit)])
        last_result = WorkspaceResult(ok=cp.returncode == 0, action="whatsapp_read", output=cp.stdout, error=cp.stderr)
        if last_result.ok:
            return last_result
    return last_result or WorkspaceResult(ok=False, action="whatsapp_read", error="WhatsApp read failed.")


async def whatsapp_search(chat: str) -> WorkspaceResult:
    last_result: WorkspaceResult | None = None
    for candidate in _chat_name_candidates(chat):
        cp = _run_script("whatsapp_search_chat.py", ["--chat", candidate])
        last_result = WorkspaceResult(ok=cp.returncode == 0, action="whatsapp_search", output=cp.stdout, error=cp.stderr)
        if last_result.ok:
            return last_result
    return last_result or WorkspaceResult(ok=False, action="whatsapp_search", error="WhatsApp search failed.")


async def dispatch_workspace_intent(
    workspace_intent: str,
    message: str,
    details: dict[str, Any],
    model: str,
) -> str:
    if workspace_intent == "gmail_send":
        to_value = details.get("email")
        subject = details.get("subject") or "Tyrone message"
        body = details.get("body") or message
        if not to_value:
            raise RuntimeError("Gmail send requests need a recipient email address.")
        result = await gmail_send(to_value, subject, body)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Gmail send failed.")
        return result.output.strip() or "Gmail send completed."

    if workspace_intent == "gmail_check":
        result = await gmail_check(5)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Gmail check failed.")
        return result.output.strip() or "No unread inbox mail."

    if workspace_intent == "calendar_create":
        title = details.get("calendar_title") or details.get("title") or "Tyrone calendar event"
        date = details.get("date")
        start = details.get("start")
        end = details.get("end")
        if not date or not start or not end:
            raise RuntimeError("Calendar create requests need a date and start/end times.")
        norm_date = normalize_date(date)
        start_dt = f"{norm_date}T{start}:00+02:00"
        end_dt = f"{norm_date}T{end}:00+02:00"
        result = await calendar_create(title, start_dt, end_dt)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Calendar create failed.")
        return result.output.strip() or "Calendar entry created."

    if workspace_intent == "calendar_search":
        query = details.get("title") or details.get("message") or message
        result = await calendar_search(query, days=7)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Calendar search failed.")
        return summarize_calendar_output(result.output, message)

    if workspace_intent == "calendar_remove":
        event_id = details.get("event_id") or details.get("id")
        if not event_id:
            raise RuntimeError("Calendar remove requests need an event ID.")
        result = await calendar_remove(event_id)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Calendar remove failed.")
        return result.output.strip() or "Calendar entry removed."

    if workspace_intent == "calendar_next":
        request_l = message.lower()
        if "tomorrow" in request_l or "today" in request_l:
            tz = ZoneInfo("Africa/Johannesburg")
            now = datetime.now(tz)
            day_offset = 1 if "tomorrow" in request_l else 0
            target_day = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_start = target_day.isoformat()
            day_end = (target_day + timedelta(days=1)).isoformat()
            result = await calendar_search("", time_min=day_start, time_max=day_end, max_results=20)
            if not result.ok:
                raise RuntimeError(result.error.strip() or "Calendar search failed.")
            summary = summarize_calendar_output(result.output, message)
            return summary or "No calendar entries found for that day."

        result = await calendar_next(5)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Calendar next failed.")
        return summarize_calendar_output(result.output, message)

    if workspace_intent == "sheet_create":
        title = details.get("title") or "Tyrone Sheet"
        result = await sheet_create(title)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Sheet create failed.")
        return result.output.strip() or "Spreadsheet created."

    if workspace_intent == "sheet_read":
        spreadsheet_id = details.get("spreadsheet_id")
        range_name = details.get("range")
        if not spreadsheet_id or not range_name:
            raise RuntimeError("Sheet read requests need a spreadsheet id and range.")
        result = await sheet_read(spreadsheet_id, range_name)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Sheet read failed.")
        return result.output.strip() or "No sheet values found."

    if workspace_intent == "sheet_write":
        spreadsheet_id = details.get("spreadsheet_id")
        range_name = details.get("range")
        values_json = details.get("values")
        if not spreadsheet_id or not range_name or not values_json:
            raise RuntimeError("Sheet write requests need a spreadsheet id, range, and values JSON.")
        result = await sheet_write(spreadsheet_id, range_name, values_json)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "Sheet write failed.")
        return result.output.strip() or "Sheet write completed."

    if workspace_intent == "whatsapp_send":
        chat = details.get("chat")
        if not chat:
            raise RuntimeError("WhatsApp send requests need a chat name.")
        message_text = details.get("whatsapp_message") or details.get("body") or message
        result = await whatsapp_send(chat, message=message_text)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "WhatsApp send failed.")
        return result.output.strip() or "WhatsApp message sent."

    if workspace_intent == "whatsapp_read":
        chat = details.get("chat")
        if not chat:
            raise RuntimeError("WhatsApp read requests need a chat name.")
        result = await whatsapp_read(chat, limit=10)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "WhatsApp read failed.")
        user_text = message.lower()
        if any(term in user_text for term in ("plumber", "plumbers", "recommended", "recommend", "meeting date", "decided", "decision", "summary", "summarize", "summarise")):
            style_hint = (
                "Return a compact answer with at most 5 bullets. "
                "Only mention people, decisions, or facts that are explicitly supported by the messages. "
                "If the chat does not clearly support an answer, say that you do not know. "
                "For recommendation requests, list only the names that are directly mentioned as recommendations and a very short reason. "
                "For decision requests, answer yes/no first, then one short sentence. "
                "Avoid long prose, avoid repeating the whole transcript, and exclude timestamps and phone numbers unless they are directly relevant."
            )
        else:
            style_hint = (
                "Return a concise answer in at most 4 bullets. "
                "Focus on the main point, any decision, and any action items. "
                "Avoid timestamps, phone numbers, and repeated chatter."
            )
        answer_prompt = (
            "Answer the user's WhatsApp question using only the retrieved chat messages below. "
            f"{style_hint}\n\n"
            f"User question: {message}\n\n"
            f"Chat messages:\n{result.output}"
        )
        answer_response, _, answer_error = await ollama_chat(
            model,
            answer_prompt,
            temperature=0.1,
        )
        if answer_error:
            raise RuntimeError(answer_error)
        return answer_response.get("message", {}).get("content", "").strip() or summarize_whatsapp_output(result.output)

    if workspace_intent == "whatsapp_search":
        chat = details.get("chat")
        if not chat:
            raise RuntimeError("WhatsApp search requests need a chat name.")
        result = await whatsapp_search(chat)
        if not result.ok:
            raise RuntimeError(result.error.strip() or "WhatsApp search failed.")
        return result.output.strip() or f"Chat opened: {chat}"

    raise RuntimeError(f"Unsupported workspace intent: {workspace_intent}")

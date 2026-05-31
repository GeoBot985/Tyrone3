from datetime import datetime, timezone
from models import TurnContext, WatcherEvent

def log_event(context: TurnContext, stage: str, decision: str, notes: str):
    preview = context.user_message[:50] + ("..." if len(context.user_message) > 50 else "")
    event = WatcherEvent(
        stage=stage,
        timestamp=datetime.now(timezone.utc).isoformat(),
        decision=decision,
        notes=notes,
        selected_model=context.model,
        user_message_preview=preview
    )
    context.watcher_events.append(event)

class PassiveWatcher:
    def pre_check(self, context: TurnContext) -> bool:
        """
        Passive watcher pre_check. Emits an event but does not block.
        """
        log_event(
            context,
            stage="pre_ollama",
            decision="allow",
            notes="Passive watcher allowing request through"
        )
        return True

    def post_check(self, context: TurnContext) -> bool:
        """
        Passive watcher post_check. Emits an event but does not block.
        """
        log_event(
            context,
            stage="post_ollama",
            decision="allow",
            notes="Passive watcher allowing response through"
        )
        return True

import asyncio
import inspect
import uuid
from functools import wraps
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from ..primitive.environment import ENVIRONMENT, EnvironmentsEnum

try:
    from IPython.display import HTML, display  # type: ignore
except Exception:
    HTML = None
    display = None

# One channel per kernel process: an abort reaches the loops of this kernel only.
ABORT_CHANNEL_NAME = f"mat3ra_abort_{uuid.uuid4().hex}"


class UserAbortError(RuntimeError):
    pass


def display_abort_controls_in_current_cell_output(
    channel_name: str = ABORT_CHANNEL_NAME,
    abort_button_text: str = "Stop polling",
) -> None:
    """
    Shows:
      [Stop polling] Press ESC to abort

    Only works in notebook frontends that support HTML output.
    Safe no-op otherwise.
    """
    if HTML is None or display is None:
        return

    element_id = f"abort_controls_{uuid.uuid4().hex}"

    display(
        HTML(
            f"""
            <div style="display:flex; align-items:center; gap:12px; margin:8px 0;">
              <button
                id="{element_id}_button"
                style="
                  background:#d32f2f; color:white; border:none; padding:8px 14px;
                  border-radius:6px; cursor:pointer; font-weight:600;
                "
              >{abort_button_text}</button>

              <span style="font-family:monospace; opacity:0.85;">Press ESC to abort</span>
              <span id="{element_id}_status" style="font-family:monospace; opacity:0.85;"></span>
            </div>

            <script>
            (function() {{
              const channelName = {channel_name!r};

              // Install ESC broadcaster once per page; ESC aborts the loop of the notebook in focus only
              if (!window.__mat3raAbortChannels) {{
                window.__mat3raAbortChannels = new Map();
                document.addEventListener("keydown", (event) => {{
                  const notebookPanel = document.querySelector(".jp-NotebookPanel.jp-mod-current");
                  window.__mat3raAbortChannels.forEach((buttonChannel, buttonElement) => {{
                    if (event.key === "Escape" && notebookPanel?.contains(buttonElement)) {{
                      buttonChannel.postMessage({{ type: "abort", source: "escape" }});
                    }}
                  }});
                }}, true);
              }}

              // Button broadcaster (this output)
              const buttonChannel = new BroadcastChannel(channelName);
              const buttonElement = document.getElementById("{element_id}_button");
              const statusElement = document.getElementById("{element_id}_status");
              if (!buttonElement) return;
              window.__mat3raAbortChannels.set(buttonElement, buttonChannel);

              buttonElement.addEventListener("click", () => {{
                buttonChannel.postMessage({{ type: "abort", source: "button" }});
                if (statusElement) {{
                  statusElement.textContent = "Abort sent";
                  statusElement.style.color = "#d32f2f";
                }}
              }});
            }})();
            </script>
            """
        )
    )


class BroadcastChannelAbortController(BaseModel):
    """
    WebWorker-side receiver. Works only in pyodide (emscripten).
    An abort message cancels the task running the loop and aborts the fetch given `fetch_abort_signal`.
    In regular Python: start() does nothing and `fetch_abort_signal` stays None.
    """

    channel_name: str = ABORT_CHANNEL_NAME

    def model_post_init(self, __context: Any) -> None:
        self._broadcast_channel = None
        self._on_message_proxy = None
        self._fetch_abort_controller = None

    @property
    def fetch_abort_signal(self) -> Any:
        return getattr(self._fetch_abort_controller, "signal", None)

    def start(self, task: "asyncio.Task[Any]") -> None:
        if ENVIRONMENT != EnvironmentsEnum.PYODIDE:
            return
        if self._broadcast_channel is not None:
            return

        import js  # type: ignore
        from pyodide.ffi import create_proxy  # type: ignore

        self._broadcast_channel = js.BroadcastChannel.new(self.channel_name)
        self._fetch_abort_controller = js.AbortController.new()

        def on_message(event) -> None:
            message = getattr(event, "data", None)
            if message and getattr(message, "type", None) == "abort":
                self._fetch_abort_controller.abort()  # type: ignore
                task.cancel()

        self._on_message_proxy = create_proxy(on_message)
        self._broadcast_channel.onmessage = self._on_message_proxy  # type: ignore

    def stop(self) -> None:
        if self._broadcast_channel is None:
            return

        self._broadcast_channel.close()
        self._broadcast_channel = None

        if self._on_message_proxy is not None:
            self._on_message_proxy.destroy()
            self._on_message_proxy = None


async def run_interruptible_loop_async(
    loop_body: Callable[[Any], Awaitable[bool]],
    poll_interval_seconds: float,
    *,
    channel_name: str = ABORT_CHANNEL_NAME,
    show_controls: bool = True,
) -> None:
    """
    Wraps an async loop around a "poll" function that returns True to continue, False to stop.

    loop_body(abort_signal):
      - do one "poll" iteration; `abort_signal` aborts its fetch (pyodide), None in regular Python
      - return True to keep looping, False to stop normally

    pyodide: ESC/button cancels the task running the loop, during a poll or the sleep, raising UserAbortError.
    regular Python: Ctrl+C/Stop interrupts the kernel.
    """
    broadcast_channel_abort_controller = BroadcastChannelAbortController(channel_name=channel_name)
    broadcast_channel_abort_controller.start(asyncio.current_task())  # type: ignore

    if show_controls and ENVIRONMENT == EnvironmentsEnum.PYODIDE:
        display_abort_controls_in_current_cell_output(channel_name=channel_name, abort_button_text="Abort")

    try:
        while await loop_body(broadcast_channel_abort_controller.fetch_abort_signal):
            await asyncio.sleep(poll_interval_seconds)
    except asyncio.CancelledError:
        raise UserAbortError("Aborted by user.") from None
    finally:
        broadcast_channel_abort_controller.stop()


def interruptible_polling_loop(
    poll_interval_kwarg_name: str = "poll_interval",
    *,
    default_poll_interval_seconds: float = 10.0,
    channel_name: str = ABORT_CHANNEL_NAME,
    show_controls: bool = True,
):
    """
    Turns a poll-step function into an async loop. Wrapped fn returns True to continue, False to stop.
    ESC/Abort (notebooks) raises UserAbortError at once, during a poll or the sleep; Ctrl+C natively.
    Poll interval: kwarg poll_interval_kwarg_name, else default_poll_interval_seconds.
    """

    def decorator(poll_step_function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(poll_step_function)
        async def wrapped(*args: Any, **kwargs: Any) -> None:
            poll_interval_seconds = float(kwargs.pop(poll_interval_kwarg_name, default_poll_interval_seconds))

            async def loop_body(abort_signal: Any) -> bool:
                result = poll_step_function(*args, **kwargs)
                should_continue = await result if inspect.isawaitable(result) else result
                return bool(should_continue)

            await run_interruptible_loop_async(
                loop_body,
                poll_interval_seconds,
                channel_name=channel_name,
                show_controls=show_controls,
            )

        return wrapped

    return decorator

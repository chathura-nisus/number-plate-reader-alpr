import logging
from datetime import datetime as dt


class LoggingService:
    def __init__(self, socketio_instance=None):
        self.socketio = socketio_instance
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.log_raw = logging  # Expose raw logging for critical/exception cases

    def set_socketio(self, socketio_instance):
        """Allows setting socketio instance after initialization if needed."""
        self.socketio = socketio_instance

    def web_log(self, message, level="info", exc_info=False):
        log_message = f"WEB_UI_LOG ({level.upper()}): {message}"

        if level == "error":
            self.log_raw.error(log_message, exc_info=exc_info)
        elif level == "warn" or level == "warning":
            self.log_raw.warning(log_message, exc_info=exc_info)
        elif level == "critical":
            self.log_raw.critical(log_message, exc_info=exc_info)
        else:  # info, debug, etc.
            self.log_raw.info(log_message, exc_info=exc_info)

        if self.socketio:
            timestamp = dt.now().strftime("%H:%M:%S")
            try:
                self.socketio.emit('new_log', {'level': level, 'message': f"[{timestamp}] {message}"})
            except Exception as e:
                self.log_raw.error(f"Failed to emit log via SocketIO: {e}")
        else:
            # Fallback if socketio is not available (e.g. during early init)
            print(f"SocketIO for web_log not set: [{dt.now().strftime('%H:%M:%S')}] {message}")

    def emit_event(self, event_name, data):
        if self.socketio:
            try:
                self.socketio.emit(event_name, data)
            except Exception as e:
                self.web_log(f"Failed to emit SocketIO event '{event_name}': {e}", "error")
        else:
            self.web_log(f"SocketIO not available to emit event '{event_name}'", "warn")

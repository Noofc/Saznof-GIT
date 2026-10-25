import logging
import sys
import os
from datetime import datetime
from typing import Optional
from functions.timezone import brasilia_now

class ColoredFormatter(logging.Formatter):
    """Formatter com cores para diferentes níveis de log"""

    # Códigos ANSI para cores
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }

    RESET = '\033[0m'  # Reset color
    GRAY = '\033[90m'  # Gray for timestamps
    WHITE = '\033[37m' # White for messages

    def format(self, record):
        # Adicionar cor baseada no nível
        color = self.COLORS.get(record.levelname, self.WHITE)

        # Formatar timestamp em horário de Brasília
        brasilia_time = brasilia_now()
        timestamp = brasilia_time.strftime('%H:%M:%S')

        # Formatar a mensagem
        level = f"{color}{record.levelname:<8}{self.RESET}"
        time_str = f"{self.GRAY}[{timestamp}]{self.RESET}"
        module = f"{self.GRAY}{record.name:<15}{self.RESET}"
        message = f"{color}{record.getMessage()}{self.RESET}"

        # Formatar extras se houver
        extra = ""
        if hasattr(record, 'extra_data') and record.extra_data:
            extra = f" {self.GRAY}{record.extra_data}{self.RESET}"

        return f"{time_str} {level} {module} {message}{extra}"

class LyonLogger:
    """Sistema de logging aprimorado para o Lyon Pro"""

    def __init__(self):
        self.logger = logging.getLogger('LyonPro')
        self.logger.setLevel(logging.DEBUG)

        # Remover handlers existentes
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

        # Handler para console com cores
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(ColoredFormatter())
        self.logger.addHandler(console_handler)

        # Handler para arquivo (opcional - pode ser ativado depois)
        self.file_handler = None

    def enable_file_logging(self, log_file: str = 'logs/system_bot.log'):
        """Ativa logging para arquivo com rotação"""
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)

        # Criar diretório se não existir
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        from logging.handlers import RotatingFileHandler
        self.file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        self.file_handler.setLevel(logging.INFO)
        # Formatter sem cores para arquivo
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.file_handler.setFormatter(file_formatter)
        self.logger.addHandler(self.file_handler)

    def debug(self, message: str, extra_data: Optional[dict] = None):
        """Log de debug"""
        self._log('debug', message, extra_data)

    def info(self, message: str, extra_data: Optional[dict] = None):
        """Log informativo"""
        self._log('info', message, extra_data)

    def warning(self, message: str, extra_data: Optional[dict] = None):
        """Log de aviso"""
        self._log('warning', message, extra_data)

    def error(self, message: str, extra_data: Optional[dict] = None):
        """Log de erro"""
        self._log('error', message, extra_data)

    def critical(self, message: str, extra_data: Optional[dict] = None):
        """Log crítico"""
        self._log('critical', message, extra_data)

    def command(self, user: str, command: str, channel: str, extra_data: Optional[dict] = None):
        """Log específico para comandos"""
        message = f"Comando executado: {command}"
        extra = {
            'user': user,
            'channel': channel,
            'type': 'command'
        }
        if extra_data:
            extra.update(extra_data)
        self.info(message, extra)

    def event(self, event_type: str, details: dict, extra_data: Optional[dict] = None):
        """Log específico para eventos"""
        message = f"Evento: {event_type}"
        extra = {
            'event_type': event_type,
            'details': details,
            'type': 'event'
        }
        if extra_data:
            extra.update(extra_data)
        self.info(message, extra)

    def performance(self, operation: str, duration: float, extra_data: Optional[dict] = None):
        """Log específico para performance"""
        message = f"Performance: {operation} - {duration:.2f}s"
        extra = {
            'operation': operation,
            'duration': duration,
            'type': 'performance'
        }
        if extra_data:
            extra.update(extra_data)
        self.info(message, extra)

    def _log(self, level: str, message: str, extra_data: Optional[dict] = None):
        """Método interno para logging"""
        record = logging.LogRecord(
            name=self.logger.name,
            level=getattr(logging, level.upper()),
            pathname='',
            lineno=0,
            msg=message,
            args=(),
            exc_info=None
        )

        if extra_data:
            record.extra_data = str(extra_data)

        self.logger.handle(record)

# Instância global do logger
logger = LyonLogger()

# Função de compatibilidade para código existente
def log_command(user: str, command: str, channel: str = ""):
    """Função de compatibilidade para logs de comando existentes"""
    logger.command(user, command, channel)

def log_event(event_type: str, details: dict):
    """Função de compatibilidade para logs de evento existentes"""
    logger.event(event_type, details)
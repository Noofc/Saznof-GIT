# -*- coding: utf-8 -*-
"""
Sistema de gerenciamento de timezone para o bot
Salva tudo em UTC, converte apenas para exibição
"""

from datetime import datetime, timezone
import pytz
from typing import Optional
from functions.database import database as db
import time

# Timezones permitidos
ALLOWED_TIMEZONES = {
    "America/Sao_Paulo",
    "America/Manaus", 
    "America/Rio_Branco",
    "America/Bahia",
    "America/Fortaleza",
    "America/Araguaina",
    "America/Maceio",
    "America/Recife",
    "America/Anchorage",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/New_York",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Hong_Kong",
    "Asia/Singapore",
    "Australia/Sydney",
}

DEFAULT_TIMEZONE = "America/Sao_Paulo"


class TimezoneManager:
    """Gerencia timezones de servidor e usuário"""
    
    _tz_cache = {}
    _cache_ttl = 300  # 5 minutos
    _cache_timestamps = {}
    
    @staticmethod
    def get_tz_object(timezone_name: str) -> Optional[pytz.timezone]:
        """Obtém objeto de timezone com cache"""
        if timezone_name not in TimezoneManager._tz_cache:
            try:
                TimezoneManager._tz_cache[timezone_name] = pytz.timezone(timezone_name)
                TimezoneManager._cache_timestamps[timezone_name] = time.time()
            except pytz.exceptions.UnknownTimeZoneError:
                return None
        return TimezoneManager._tz_cache[timezone_name]
    
    @staticmethod
    def get_server_timezone(guild_id: int) -> str:
        """Obtém timezone configurado para o servidor"""
        try:
            settings = db.get_document("loja_timezone_settings") or {}
            server_tzs = settings.get("server_timezones", {})
            tz = server_tzs.get(str(guild_id), DEFAULT_TIMEZONE)
            
            # Validar se timezone é permitido
            if tz not in ALLOWED_TIMEZONES:
                tz = DEFAULT_TIMEZONE
            
            return tz
        except:
            return DEFAULT_TIMEZONE
    
    @staticmethod
    def get_user_timezone(user_id: int, guild_id: int) -> str:
        """Obtém timezone do usuário (futura funcionalidade)"""
        # Por enquanto, usar timezone do servidor
        return TimezoneManager.get_server_timezone(guild_id)
    
    @staticmethod
    def set_server_timezone(guild_id: int, timezone_name: str) -> bool:
        """Define timezone para o servidor"""
        if timezone_name not in ALLOWED_TIMEZONES:
            return False
        
        try:
            settings = db.get_document("loja_timezone_settings") or {}
            if "server_timezones" not in settings:
                settings["server_timezones"] = {}
            
            settings["server_timezones"][str(guild_id)] = timezone_name
            db.save_document("loja_timezone_settings", settings)
            return True
        except:
            return False
    
    @staticmethod
    def get_utc_now() -> datetime:
        """Retorna agora em UTC com informação de timezone"""
        return datetime.now(timezone.utc)
    
    @staticmethod
    def utc_to_display(utc_dt: Optional[datetime], timezone_name: str = None) -> datetime:
        """Converte datetime UTC para timezone de exibição"""
        if utc_dt is None:
            utc_dt = TimezoneManager.get_utc_now()
        
        if timezone_name is None:
            timezone_name = DEFAULT_TIMEZONE
        
        tz = TimezoneManager.get_tz_object(timezone_name)
        if tz is None:
            tz = TimezoneManager.get_tz_object(DEFAULT_TIMEZONE)
        
        # Se datetime não tem tzinfo, assumir UTC
        if utc_dt.tzinfo is None:
            utc_dt = pytz.UTC.localize(utc_dt)
        
        return utc_dt.astimezone(tz)
    
    @staticmethod
    def format_datetime_br(
        utc_dt: Optional[datetime] = None,
        timezone_name: str = None,
        show_time: bool = True,
        show_seconds: bool = True
    ) -> str:
        """Formata datetime para formato brasileiro sem mostrar GMT/timezone"""
        if utc_dt is None:
            utc_dt = TimezoneManager.get_utc_now()
        
        if timezone_name is None:
            timezone_name = DEFAULT_TIMEZONE
        
        # Converter para timezone local
        display_dt = TimezoneManager.utc_to_display(utc_dt, timezone_name)
        
        # Formatar: DD/MM/YYYY
        date_str = display_dt.strftime("%d/%m/%Y")
        
        if show_time:
            if show_seconds:
                time_str = display_dt.strftime("%H:%M:%S")
            else:
                time_str = display_dt.strftime("%H:%M")
            return f"{date_str} {time_str}"
        
        return date_str
    
    @staticmethod
    def format_date_br(utc_dt: Optional[datetime] = None, timezone_name: str = None) -> str:
        """Formata apenas a data em formato brasileiro"""
        return TimezoneManager.format_datetime_br(utc_dt, timezone_name, show_time=False)
    
    @staticmethod
    def format_time_br(utc_dt: Optional[datetime] = None, timezone_name: str = None, show_seconds: bool = True) -> str:
        """Formata apenas a hora"""
        if utc_dt is None:
            utc_dt = TimezoneManager.get_utc_now()
        
        if timezone_name is None:
            timezone_name = DEFAULT_TIMEZONE
        
        display_dt = TimezoneManager.utc_to_display(utc_dt, timezone_name)
        
        if show_seconds:
            return display_dt.strftime("%H:%M:%S")
        else:
            return display_dt.strftime("%H:%M")
    
    @staticmethod
    def get_utc_timestamp(dt: Optional[datetime] = None) -> int:
        """Retorna timestamp Unix (UTC) para armazenar no banco"""
        if dt is None:
            dt = TimezoneManager.get_utc_now()
        
        return int(dt.timestamp())
    
    @staticmethod
    def from_timestamp(timestamp: int) -> datetime:
        """Converte timestamp Unix para datetime UTC"""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)


# Funções de conveniência
def get_utc_now() -> datetime:
    """Retorna agora em UTC"""
    return TimezoneManager.get_utc_now()

def format_receipt_time(utc_dt: Optional[datetime] = None, guild_id: int = None) -> tuple:
    """Retorna (data, hora) formatada para comprovante"""
    tz = DEFAULT_TIMEZONE
    if guild_id:
        tz = TimezoneManager.get_server_timezone(guild_id)
    
    date = TimezoneManager.format_date_br(utc_dt, tz)
    time = TimezoneManager.format_time_br(utc_dt, tz, show_seconds=True)
    return (date, time)

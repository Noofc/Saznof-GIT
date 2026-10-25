#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exemplo de uso do sistema de logging aprimorado
"""

import _path  # noqa: F401
from functions.logger import logger

def exemplo_logs():
    """Demonstra diferentes tipos de logs"""

    print("🎯 Demonstrando Sistema de Logging Aprimorado\n")

    # Logs básicos
    logger.debug("Iniciando sistema de demonstração")
    logger.info("Sistema inicializado com sucesso")
    logger.warning("Configuração padrão sendo usada")

    # Log de comando
    logger.command(
        user="João Silva#1234",
        command="/ticket criar",
        channel="#suporte",
        extra_data={"priority": "alta", "category": "bug"}
    )

    # Log de evento
    logger.event(
        event_type="member_join",
        details={
            "user": "Maria Santos#5678",
            "user_id": 987654321,
            "guild": "Lyon Pro Server"
        }
    )

    # Log de performance
    logger.performance(
        operation="process_ticket_creation",
        duration=0.234,
        extra_data={"ticket_id": 12345}
    )

    # Logs de erro
    logger.error("Falha ao conectar com banco de dados")
    logger.critical("Sistema de backup falhou - intervenção manual necessária")

    print("\n✅ Demonstração concluída!")
    print("💡 Para ativar logs em arquivo, use: logger.enable_file_logging()")

if __name__ == "__main__":
    exemplo_logs()

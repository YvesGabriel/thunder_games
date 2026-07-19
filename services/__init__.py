"""Adaptadores de serviços externos (voicebox, telegram, claude, ...).

Cada módulo aqui fala com UMA integração e é o único que conhece o detalhe dela.
A orquestração (channel/pipeline) usa estes adaptadores sem saber de HTTP/CLI.
"""

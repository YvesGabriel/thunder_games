#!/usr/bin/env python3
"""Entrada do orquestrador — a lógica agora vive em channel/.

Mantém `python pipeline.py <cmd> ...` e a invocação do bot funcionando; só delega
pra channel.pipeline. A montagem do roteiro está em channel/roteiro.py e os
utilitários em channel/common.py.
"""

import sys

from channel.pipeline import main

if __name__ == "__main__":
    sys.exit(main())

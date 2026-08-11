"""
Equipamento inicial por classe (SRD 5.1).

GERADO por `ingestor/gerar_equipamento_inicial.py` — NÃO editar à mão.
Só o equipamento FIXO. As opções de escolha do SRD ('escolha uma arma
marcial') NÃO entram: escolher pelo jogador seria decidir a build dele.
"""

from typing import Any

EQUIPAMENTO_INICIAL: dict[str, list[dict[str, Any]]] = {'Bardo': [{'nome': 'Armadura de couro', 'quantidade': 1}, {'nome': 'Adaga', 'quantidade': 1}],
 'Bruxo': [{'nome': 'Adaga', 'quantidade': 2}, {'nome': 'Armadura de couro', 'quantidade': 1}],
 'Bárbaro': [{'nome': 'Mochila de explorador', 'quantidade': 1},
             {'nome': 'Azagaia', 'quantidade': 4}],
 'Clérigo': [{'nome': 'Escudo', 'quantidade': 1}],
 'Druida': [{'nome': 'Armadura de couro', 'quantidade': 1},
            {'nome': 'Mochila de explorador', 'quantidade': 1}],
 'Feiticeiro': [{'nome': 'Adaga', 'quantidade': 2}],
 'Guerreiro': [],
 'Ladino': [{'nome': 'Armadura de couro', 'quantidade': 1},
            {'nome': 'Adaga', 'quantidade': 2},
            {'nome': 'Ferramentas de ladrão', 'quantidade': 1}],
 'Mago': [{'nome': 'Grimório', 'quantidade': 1}],
 'Monge': [{'nome': 'Dardo', 'quantidade': 10}],
 'Paladino': [{'nome': 'Cota de malha', 'quantidade': 1}],
 'Ranger': [{'nome': 'Arco longo', 'quantidade': 1}, {'nome': 'Flecha', 'quantidade': 20}]}

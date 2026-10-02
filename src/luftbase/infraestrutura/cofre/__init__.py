"""Acesso tipado e testavel aos segredos mantidos no Vault."""

from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.contratos import DesprotetorSegredo, ProvedorSegredos
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais

__all__ = [
    "CarregadorCredenciais",
    "ClienteVaultHvac",
    "CredencialBanco",
    "DesprotetorFernet",
    "DesprotetorSegredo",
    "ProvedorSegredos",
    "Segredo",
    "TipoBanco",
]

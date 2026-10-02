"""Objetos de identidade usados uniformemente por todas as aplicacoes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """Retrato serializavel do usuario, sem manter uma entidade ORM conectada."""

    id_usuario: int
    login: str
    nome_completo: str
    email: str | None
    id_grupo: int | None
    nome_grupo: str | None
    permissoes: frozenset[str] = field(default_factory=frozenset)
    foto_perfil: str | None = None
    status_online: bool = True
    cargo: str | None = None
    departamento: str | None = None
    telefone: str | None = None
    celular: str | None = None
    unidade_filial: str | None = None
    tema_preferido: str = "luft"
    modo_tema: str = "SISTEMA"
    idioma: str = "pt-BR"

    @property
    def codigo_usuario(self) -> int:
        """Alias alinhado a chave de usuario corporativa."""
        return self.id_usuario

    @property
    def login_usuario(self) -> str:
        """Alias alinhado a tb_usuario."""
        return self.login

    @property
    def nome_usuario(self) -> str:
        """Alias alinhado a tb_usuario."""
        return self.nome_completo

    @property
    def email_usuario(self) -> str | None:
        """Alias alinhado a tb_usuario."""
        return self.email

    @property
    def codigo_usuariogrupo(self) -> int | None:
        """Alias alinhado a tb_usuario."""
        return self.id_grupo

    @property
    def sigla_usuariogrupo(self) -> str | None:
        """Alias alinhado a tb_usuario."""
        return self.nome_grupo

    @property
    def cargo_usuario(self) -> str | None:
        """Alias funcional alinhado a tb_usuario."""
        return self.cargo

    @property
    def departamento_usuario(self) -> str | None:
        """Alias departamental alinhado a tb_usuario."""
        return self.departamento

    @property
    def telefone_usuario(self) -> str | None:
        """Alias de contato alinhado a tb_usuario."""
        return self.telefone

    @property
    def celular_usuario(self) -> str | None:
        """Alias de contato celular alinhado a tb_usuario."""
        return self.celular

    @property
    def is_authenticated(self) -> bool:
        """Indica compatibilidade com o contrato esperado pelo Flask-Login."""

        return True

    @property
    def is_active(self) -> bool:
        """Indica que a identidade carregada pode participar da sessao."""

        return True

    @property
    def is_anonymous(self) -> bool:
        """Uma identidade autenticada nunca e anonima."""

        return False

    def get_id(self) -> str:
        """Devolve o identificador textual exigido pelo Flask-Login."""

        return str(self.id_usuario)

    def possui_permissao(self, chave: str) -> bool:
        """Consulta somente o retrato ja carregado, sem acessar banco."""

        return chave in self.permissoes

    def como_dict(self) -> dict[str, object]:
        """Produz o retrato JSON armazenado na sessao compartilhada."""

        return {
            "id_usuario": self.id_usuario,
            "login": self.login,
            "nome_completo": self.nome_completo,
            "email": self.email,
            "id_grupo": self.id_grupo,
            "nome_grupo": self.nome_grupo,
            "permissoes": sorted(self.permissoes),
            "foto_perfil": self.foto_perfil,
            "status_online": self.status_online,
            "cargo": self.cargo,
            "departamento": self.departamento,
            "telefone": self.telefone,
            "celular": self.celular,
            "unidade_filial": self.unidade_filial,
            "tema_preferido": self.tema_preferido,
            "modo_tema": self.modo_tema,
            "idioma": self.idioma,
        }

    @classmethod
    def de_dict(cls, dados: Mapping[str, object]) -> UsuarioAutenticado:
        """Restaura um retrato somente quando todos os tipos sao confiaveis."""

        id_usuario = dados.get("id_usuario")
        login = dados.get("login")
        nome_completo = dados.get("nome_completo")
        email = dados.get("email")
        id_grupo = dados.get("id_grupo")
        nome_grupo = dados.get("nome_grupo")
        permissoes = dados.get("permissoes", [])
        foto_perfil = dados.get("foto_perfil")
        status_online = bool(dados.get("status_online", True))
        cargo = dados.get("cargo")
        departamento = dados.get("departamento")
        telefone = dados.get("telefone")
        celular = dados.get("celular")
        unidade_filial = dados.get("unidade_filial")
        tema_preferido = str(dados.get("tema_preferido") or "luft")
        modo_tema = str(dados.get("modo_tema") or "SISTEMA")
        idioma = str(dados.get("idioma") or "pt-BR")

        if isinstance(id_usuario, bool) or not isinstance(id_usuario, int) or id_usuario <= 0:
            raise ValueError("O retrato de usuario possui identificador invalido.")
        if not isinstance(login, str) or not login.strip():
            raise ValueError("O retrato de usuario possui login invalido.")
        if not isinstance(nome_completo, str) or not nome_completo.strip():
            raise ValueError("O retrato de usuario possui nome invalido.")
        if email is not None and not isinstance(email, str):
            raise ValueError("O retrato de usuario possui e-mail invalido.")
        if id_grupo is not None and (isinstance(id_grupo, bool) or not isinstance(id_grupo, int)):
            raise ValueError("O retrato de usuario possui grupo invalido.")
        if nome_grupo is not None and not isinstance(nome_grupo, str):
            raise ValueError("O retrato de usuario possui nome de grupo invalido.")
        if foto_perfil is not None and not isinstance(foto_perfil, str):
            foto_perfil = None
        if not isinstance(permissoes, list) or not all(
            isinstance(permissao, str) and permissao for permissao in permissoes
        ):
            raise ValueError("O retrato de usuario possui permissoes invalidas.")

        return cls(
            id_usuario=id_usuario,
            login=login.strip(),
            nome_completo=nome_completo.strip(),
            email=email.strip() or None if isinstance(email, str) else None,
            id_grupo=id_grupo,
            nome_grupo=nome_grupo.strip() or None if isinstance(nome_grupo, str) else None,
            permissoes=frozenset(permissoes),
            foto_perfil=foto_perfil,
            status_online=status_online,
            cargo=cargo.strip() or None if isinstance(cargo, str) else None,
            departamento=departamento.strip() or None if isinstance(departamento, str) else None,
            telefone=telefone.strip() or None if isinstance(telefone, str) else None,
            celular=celular.strip() or None if isinstance(celular, str) else None,
            unidade_filial=unidade_filial.strip() or None if isinstance(unidade_filial, str) else None,
            tema_preferido=tema_preferido,
            modo_tema=modo_tema,
            idioma=idioma,
        )

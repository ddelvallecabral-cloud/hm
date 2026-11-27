"""Contexto de auditoría: usuario e IP del request en curso.

`AuditoriaMiddleware` los guarda en ContextVars; `AuditableModel` los lee al
escribir en la bitácora. Fuera de un request (shell, comandos, tareas) use
`contexto_auditoria(usuario)` para que los cambios queden atribuidos.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_usuario: ContextVar = ContextVar("auditoria_usuario", default=None)
_ip: ContextVar = ContextVar("auditoria_ip", default=None)


def usuario_actual():
    return _usuario.get()


def ip_actual():
    return _ip.get()


@contextmanager
def contexto_auditoria(usuario, ip=None):
    t1, t2 = _usuario.set(usuario), _ip.set(ip)
    try:
        yield
    finally:
        _usuario.reset(t1)
        _ip.reset(t2)


def _ip_de(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    return reenviada.split(",")[0].strip() if reenviada else request.META.get("REMOTE_ADDR")


class AuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # request.user es perezoso: DRF autentica dentro de la vista, por eso
        # se guarda el request y se resuelve el usuario al momento de auditar.
        t1, t2 = _usuario.set(_UsuarioPerezoso(request)), _ip.set(_ip_de(request))
        try:
            return self.get_response(request)
        finally:
            _usuario.reset(t1)
            _ip.reset(t2)


class _UsuarioPerezoso:
    def __init__(self, request):
        self.request = request

    def resolver(self):
        u = getattr(self.request, "user", None)
        return u if u is not None and u.is_authenticated else None


def resolver_usuario():
    u = usuario_actual()
    if isinstance(u, _UsuarioPerezoso):
        return u.resolver()
    return u

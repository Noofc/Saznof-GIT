TRUTHY_VALUES = {
    True,
    1,
    "1",
    "true",
    "True",
    "TRUE",
    "on",
    "ON",
    "yes",
    "YES",
    "sim",
    "Sim",
    "SIM",
    "ativo",
    "Ativo",
    "ATIVO",
    "ativado",
    "Ativado",
    "ATIVADO",
    "habilitado",
    "Habilitado",
    "HABILITADO",
    "ligado",
    "Ligado",
    "LIGADO",
    "enabled",
}

FALSY_VALUES = {
    False,
    0,
    None,
    "",
    "0",
    "false",
    "False",
    "FALSE",
    "off",
    "OFF",
    "no",
    "NO",
    "nao",
    "Nao",
    "NAO",
    "não",
    "Não",
    "NÃO",
    "inativo",
    "Inativo",
    "INATIVO",
    "desativado",
    "Desativado",
    "DESATIVADO",
    "desabilitado",
    "Desabilitado",
    "DESABILITADO",
    "desligado",
    "Desligado",
    "DESLIGADO",
    "disabled",
}


def as_bool(value, default: bool = False) -> bool:
    try:
        if value in TRUTHY_VALUES:
            return True
        if value in FALSY_VALUES:
            return False
    except TypeError:
        return default
    return default

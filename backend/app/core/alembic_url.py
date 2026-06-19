def escape_configparser_url(value: str) -> str:
    return value.replace("%", "%%")

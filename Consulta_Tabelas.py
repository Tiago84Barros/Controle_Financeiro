import streamlit as st
import pandas as pd

from datetime import date
from dateutil.relativedelta import relativedelta

# Se o get_connection estiver em outro arquivo (ex: app.py, db.py etc),
# importa daqui. Exemplo:
# from app import get_connection
# ou
# from db import get_connection

# Se não tiver como importar, copia aqui a mesma função get_connection
# que você usa nas outras páginas.


MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def carregar_opcoes(conn, tabela, tipo=None):
    base_where = []
    params = []

    if tabela == "controle" and tipo is not None:
        base_where.append("tipo = %s")
        params.append(tipo)

    where_sql = ""
    if base_where:
        where_sql = "WHERE " + " AND ".join(base_where)

    # Categorias
    query_cat = f"""
        SELECT DISTINCT categoria
        FROM {tabela}
        {where_sql}
        ORDER BY categoria
    """
    df_cat = pd.read_sql(query_cat, conn, params=params)
    categorias = df_cat["categoria"].dropna().tolist()

    # Anos
    query_ano = f"""
        SELECT DISTINCT EXTRACT(YEAR FROM data)::int AS ano
        FROM {tabela}
        {where_sql}
        ORDER BY ano DESC
    """
    df_ano = pd.read_sql(query_ano, conn, params=params)
    anos = df_ano["ano"].tolist()

    return categorias, anos


def carregar_dias(conn, tabela, tipo, ano, mes, categoria=None):
    if not ano or ano == "Todos" or not mes or mes == "Todos":
        return []

    where_clauses = ["EXTRACT(YEAR FROM data) = %s", "EXTRACT(MONTH FROM data) = %s"]
    params = [int(ano), int(mes)]

    if tabela == "controle" and tipo is not None:
        where_clauses.insert(0, "tipo = %s")
        params.insert(0, tipo)

    if categoria and categoria != "Todas":
        where_clauses.append("categoria = %s")
        params.append(categoria)

    where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT DISTINCT EXTRACT(DAY FROM data)::int AS dia
        FROM {tabela}
        {where_sql}
        ORDER BY dia
    """
    df = pd.read_sql(query, conn, params=params)
    return df["dia"].tolist()


def montar_query(tabela, tipo=None, categoria=None, ano=None, mes=None, dia=None, texto=None):
    where_clauses = []
    params = []

    if tabela == "controle" and tipo is not None:
        where_clauses.append("tipo = %s")
        params.append(tipo)

    if categoria and categoria != "Todas":
        where_clauses.append("categoria = %s")
        params.append(categoria)

    if ano and ano != "Todos":
        where_clauses.append("EXTRACT(YEAR FROM data) = %s")
        params.append(int(ano))

    if mes and mes != "Todos":
        where_clauses.append("EXTRACT(MONTH FROM data) = %s")
        params.append(int(mes))

    if dia and dia != "Todos":
        where_clauses.append("EXTRACT(DAY FROM data) = %s")
        params.append(int(dia))

    if texto:
        where_clauses.append("LOWER(descricao) LIKE %s")
        params.append(f"%{texto.lower()}%")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT *
        FROM {tabela}
        {where_sql}
        ORDER BY data DESC, id DESC
    """
    return query, params


def pagina_consulta_tabelas(get_connection):
    st.title("🔍 Consulta de lançamentos")

    conn = get_connection()

    aba = st.radio(
        "Selecione o tipo de lançamento",
        ["Entradas", "Saídas", "Investimentos"],
        horizontal=True
    )

    if aba == "Entradas":
        tabela = "controle"
        tipo = "Entrada"
    elif aba == "Saídas":
        tabela = "controle"
        tipo = "Saída"
    else:
        tabela = "investimentos"
        tipo = None

    categorias, anos = carregar_opcoes(conn, tabela, tipo)

    with st.form("filtros_busca"):
        col1, col2, col3, col4 = st.co

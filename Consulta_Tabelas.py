import streamlit as st
import pandas as pd

from datetime import date
from dateutil.relativedelta import relativedelta

# Dicionário de meses para exibição
MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def format_brl(valor):
    """Formata número em R$ com padrão brasileiro."""
    if valor is None:
        return "R$ 0,00"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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


def calcular_resumos(conn, tabela, tipo=None, categoria=None, ano=None, mes=None, texto=None):
    """
    Calcula:
      - total_ano: soma de valor no ano filtrado
      - total_mes: soma de valor no ano+mês filtrados
    sempre respeitando tipo (Entrada/Saída) e categoria se informados.
    """
    base_clauses = []
    base_params = []

    if tabela == "controle" and tipo is not None:
        base_clauses.append("tipo = %s")
        base_params.append(tipo)

    if categoria and categoria != "Todas":
        base_clauses.append("categoria = %s")
        base_params.append(categoria)

    if texto:
        base_clauses.append("LOWER(descricao) LIKE %s")
        base_params.append(f"%{texto.lower()}%")

    total_ano = None
    total_mes = None

    # Total no ano
    if ano and ano != "Todos":
        clauses_ano = base_clauses + ["EXTRACT(YEAR FROM data) = %s"]
        params_ano = base_params + [int(ano)]
        where_ano = "WHERE " + " AND ".join(clauses_ano) if clauses_ano else ""
        q_ano = f"SELECT COALESCE(SUM(valor), 0) AS total_ano FROM {tabela} {where_ano}"
        df_ano = pd.read_sql(q_ano, conn, params=params_ano)
        total_ano = df_ano["total_ano"].iloc[0]

    # Total no mês (dentro do ano)
    if ano and ano != "Todos" and mes and mes != "Todos":
        clauses_mes = base_clauses + [
            "EXTRACT(YEAR FROM data) = %s",
            "EXTRACT(MONTH FROM data) = %s",
        ]
        params_mes = base_params + [int(ano), int(mes)]
        where_mes = "WHERE " + " AND ".join(clauses_mes) if clauses_mes else ""
        q_mes = f"SELECT COALESCE(SUM(valor), 0) AS total_mes FROM {tabela} {where_mes}"
        df_mes = pd.read_sql(q_mes, conn, params=params_mes)
        total_mes = df_mes["total_mes"].iloc[0]

    return total_ano, total_mes


def pagina_consulta_tabelas(get_connection):
    st.title("🔍 Consulta de lançamentos")

    conn = get_connection()

    # Escolha da aba
    aba = st.radio(
        "Selecione o tipo de lançamento",
        ["Entradas", "Saídas", "Investimentos"],
        horizontal=True,
    )

    if aba == "Entradas":
        tabela = "controle"
        tipo = "Entrada"
    elif aba == "Saídas":
        tabela = "controle"
        tipo = "Saída"
    else:
        tabela = "investimentos"
        tipo = None  # em investimentos, você pode ter outros tipos/colunas

    # Carrega categorias e anos disponíveis para aquele contexto
    categorias, anos = carregar_opcoes(conn, tabela, tipo)

    with st.form("filtros_busca"):
        col1, col2, col3, col4 = st.columns(4)

        # Categoria
        with col1:
            categoria_opcoes = ["Todas"] + categorias if categorias else ["Todas"]
            categoria_sel = st.selectbox("Categoria", categoria_opcoes)

        # Ano
        with col2:
            ano_opcoes = ["Todos"] + anos if anos else ["Todos"]
            # Se tiver anos, deixa o mais recente como default
            index_ano = 1 if anos else 0
            ano_sel = st.selectbox("Ano", ano_opcoes, index=index_ano)

        # Mês
        with col3:
            meses_opcoes = ["Todos"] + [f"{m:02d} - {MESES[m]}" for m in MESES.keys()]
            mes_label = st.selectbox("Mês", meses_opcoes)
            if mes_label != "Todos":
                # extrai o número do mês (primeiros 2 dígitos)
                mes_sel = int(mes_label.split(" - ")[0])
            else:
                mes_sel = "Todos"

        # Dias (dependente de ano, mês, categoria)
        with col4:
            if ano_sel != "Todos" and mes_sel != "Todos":
                dias_disponiveis = carregar_dias(conn, tabela, tipo, ano_sel, mes_sel, categoria_sel)
                dia_opcoes = ["Todos"] + dias_disponiveis if dias_disponiveis else ["Todos"]
            else:
                dia_opcoes = ["Todos"]
            dia_sel = st.selectbox("Dia", dia_opcoes)

        texto_busca = st.text_input("Buscar na descrição", placeholder="Ex: supermercado, aluguel...")

        submitted = st.form_submit_button("Aplicar filtros")

    if not submitted:
        st.info("Aplique os filtros para visualizar os resultados.")
        return

    # Monta a query de detalhes
    query, params = montar_query(
        tabela=tabela,
        tipo=tipo,
        categoria=categoria_sel,
        ano=ano_sel,
        mes=mes_sel,
        dia=dia_sel,
        texto=texto_busca,
    )

    df = pd.read_sql(query, conn, params=params)

    # Se não houver resultados
    if df.empty:
        st.warning("Nenhum lançamento encontrado com os filtros selecionados.")
        return

    # Garante que a coluna valor existe
    if "valor" not in df.columns:
        st.error("A tabela não possui coluna 'valor'. Ajuste o schema ou o código.")
        return

    # Total filtrado (apenas do resultado da tabela)
    total_filtrado = df["valor"].sum()

    # Resumos mensal e anual
    total_ano, total_mes = calcular_resumos(
        conn,
        tabela=tabela,
        tipo=tipo,
        categoria=categoria_sel,
        ano=ano_sel,
        mes=mes_sel,
        texto=texto_busca,
    )

    # Exibição dos resumos
    st.subheader("📊 Resumo")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Total filtrado", format_brl(total_filtrado))
    with col_b:
        if total_ano is not None and ano_sel != "Todos":
            st.metric(f"Total no ano de {ano_sel}", format_brl(total_ano))
        else:
            st.metric("Total no ano", "–")
    with col_c:
        if total_mes is not None and ano_sel != "Todos" and mes_sel != "Todos":
            label_mes = MESES.get(mes_sel, str(mes_sel))
            st.metric(f"Total em {label_mes}/{ano_sel}", format_brl(total_mes))
        else:
            st.metric("Total no mês", "–")

    st.divider()

    # Exibição da tabela de lançamentos
    st.subheader("📄 Lançamentos")
    st.dataframe(df, use_container_width=True)

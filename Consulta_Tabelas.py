# Consulta_Tabelas.py
import streamlit as st
import pandas as pd

MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}


def format_brl(valor):
    if valor is None:
        return "R$ 0,00"
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def carregar_opcoes(conn, tipo):
    """
    Carrega categorias e anos da tabela transactions filtrando por type (entrada/saida/investimento).
    """
    params = [tipo]

    # Categorias
    query_cat = """
        SELECT DISTINCT category
        FROM transactions
        WHERE type = %s
        ORDER BY category
    """
    df_cat = pd.read_sql(query_cat, conn, params=params)
    categorias = df_cat["category"].dropna().tolist()

    # Anos
    query_ano = """
        SELECT DISTINCT EXTRACT(YEAR FROM date)::int AS ano
        FROM transactions
        WHERE type = %s
        ORDER BY ano DESC
    """
    df_ano = pd.read_sql(query_ano, conn, params=params)
    anos = df_ano["ano"].tolist()

    return categorias, anos


def carregar_dias(conn, tipo, ano, mes, categoria=None):
    if not ano or ano == "Todos" or not mes or mes == "Todos":
        return []

    where_clauses = [
        "type = %s",
        "EXTRACT(YEAR FROM date) = %s",
        "EXTRACT(MONTH FROM date) = %s",
    ]
    params = [tipo, int(ano), int(mes)]

    if categoria and categoria != "Todas":
        where_clauses.append("category = %s")
        params.append(categoria)

    where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT DISTINCT EXTRACT(DAY FROM date)::int AS dia
        FROM transactions
        {where_sql}
        ORDER BY dia
    """
    df = pd.read_sql(query, conn, params=params)
    return df["dia"].tolist()


def montar_query(tipo, categoria=None, ano=None, mes=None, dia=None, texto=None):
    where_clauses = ["type = %s"]
    params = [tipo]

    if categoria and categoria != "Todas":
        where_clauses.append("category = %s")
        params.append(categoria)

    if ano and ano != "Todos":
        where_clauses.append("EXTRACT(YEAR FROM date) = %s")
        params.append(int(ano))

    if mes and mes != "Todos":
        where_clauses.append("EXTRACT(MONTH FROM date) = %s")
        params.append(int(mes))

    if dia and dia != "Todos":
        where_clauses.append("EXTRACT(DAY FROM date) = %s")
        params.append(int(dia))

    if texto:
        where_clauses.append("LOWER(description) LIKE %s")
        params.append(f"%{texto.lower()}%")

    where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT *
        FROM transactions
        {where_sql}
        ORDER BY category, date DESC, id DESC
    """
    return query, params


def calcular_resumos(conn, tipo, categoria=None, ano=None, mes=None, texto=None):
    """
    Calcula:
      - total_ano: soma de amount no ano filtrado
      - total_mes: soma de amount no ano+mês filtrados
    Sempre respeitando type (entrada/saida/investimento) e categoria.
    """
    base_clauses = ["type = %s"]
    base_params = [tipo]

    if categoria and categoria != "Todas":
        base_clauses.append("category = %s")
        base_params.append(categoria)

    if texto:
        base_clauses.append("LOWER(description) LIKE %s")
        base_params.append(f"%{texto.lower()}%")

    total_ano = None
    total_mes = None

    # Total no ano
    if ano and ano != "Todos":
        clauses_ano = base_clauses + ["EXTRACT(YEAR FROM date) = %s"]
        params_ano = base_params + [int(ano)]
        where_ano = "WHERE " + " AND ".join(clauses_ano)
        q_ano = f"SELECT COALESCE(SUM(amount), 0) AS total_ano FROM transactions {where_ano}"
        df_ano = pd.read_sql(q_ano, conn, params=params_ano)
        total_ano = df_ano["total_ano"].iloc[0]

    # Total no mês (dentro do ano)
    if ano and ano != "Todos" and mes and mes != "Todos":
        clauses_mes = base_clauses + [
            "EXTRACT(YEAR FROM date) = %s",
            "EXTRACT(MONTH FROM date) = %s",
        ]
        params_mes = base_params + [int(ano), int(mes)]
        where_mes = "WHERE " + " AND ".join(clauses_mes)
        q_mes = f"SELECT COALESCE(SUM(amount), 0) AS total_mes FROM transactions {where_mes}"
        df_mes = pd.read_sql(q_mes, conn, params=params_mes)
        total_mes = df_mes["total_mes"].iloc[0]

    return total_ano, total_mes


def pagina_consulta_tabelas(get_connection):
    st.title("🔍 Consulta de lançamentos")

    conn = get_connection()

    # Escolha do tipo de lançamento (mesma lógica do app)
    aba = st.radio(
        "Selecione o tipo de lançamento",
        ["Entradas", "Saídas", "Investimentos"],
        horizontal=True,
    )

    if aba == "Entradas":
        tipo = "entrada"
    elif aba == "Saídas":
        tipo = "saida"
    else:
        tipo = "investimento"

    # Carrega categorias e anos para esse tipo
    categorias, anos = carregar_opcoes(conn, tipo)

    with st.form("filtros_busca"):
        col1, col2, col3, col4 = st.columns(4)

        # Categoria
        with col1:
            categoria_opcoes = ["Todas"] + categorias if categorias else ["Todas"]
            categoria_sel = st.selectbox("Categoria", categoria_opcoes)

        # Ano
        with col2:
            ano_opcoes = ["Todos"] + anos if anos else ["Todos"]
            index_ano = 1 if anos else 0
            ano_sel = st.selectbox("Ano", ano_opcoes, index=index_ano)

        # Mês
        with col3:
            meses_opcoes = ["Todos"] + [f"{m:02d} - {MESES[m]}" for m in MESES.keys()]
            mes_label = st.selectbox("Mês", meses_opcoes)
            if mes_label != "Todos":
                mes_sel = int(mes_label.split(" - ")[0])
            else:
                mes_sel = "Todos"

        # Dias
        with col4:
            if ano_sel != "Todos" and mes_sel != "Todos":
                dias_disponiveis = carregar_dias(conn, tipo, ano_sel, mes_sel, categoria_sel)
                dia_opcoes = ["Todos"] + dias_disponiveis if dias_disponiveis else ["Todos"]
            else:
                dia_opcoes = ["Todos"]
            dia_sel = st.selectbox("Dia", dia_opcoes)

        texto_busca = st.text_input("Buscar na descrição", placeholder="Ex: mercado, aluguel...")

        submitted = st.form_submit_button("Aplicar filtros")

    if not submitted:
        st.info("Aplique os filtros para visualizar os resultados.")
        return

    # Query principal
    query, params = montar_query(
        tipo=tipo,
        categoria=categoria_sel,
        ano=ano_sel,
        mes=mes_sel,
        dia=dia_sel,
        texto=texto_busca,
    )

    df = pd.read_sql(query, conn, params=params)

    if df.empty:
        st.warning("Nenhum lançamento encontrado com os filtros selecionados.")
        return

    if "amount" not in df.columns:
        st.error("A tabela 'transactions' não possui coluna 'amount'.")
        return

    total_filtrado = df["amount"].sum()

    # Resumos mês/ano
    total_ano, total_mes = calcular_resumos(
        conn,
        tipo=tipo,
        categoria=categoria_sel,
        ano=ano_sel,
        mes=mes_sel,
        texto=texto_busca,
    )

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

    st.subheader("📄 Lançamentos")

    # formata data e valor para exibição
    df_view = df.copy()
    df_view["date"] = pd.to_datetime(df_view["date"]).dt.strftime("%d/%m/%Y")
    df_view["amount"] = df_view["amount"].apply(format_brl)

    df_view = df_view.rename(
        columns={
            "type": "Tipo",
            "category": "Categoria",
            "date": "Data",
            "amount": "Valor",
            "payment_type": "Forma",
            "card_name": "Cartão",
            "installments": "Parcelas",
            "description": "Descrição",
        }
    )

    st.dataframe(df_view, use_container_width=True, hide_index=True)

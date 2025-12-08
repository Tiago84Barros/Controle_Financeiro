import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
from dateutil.relativedelta import relativedelta


# -------------------------------------------------------------------
# FUNÇÕES DE APOIO
# -------------------------------------------------------------------

def expand_installments(df: pd.DataFrame, due_day: int) -> pd.DataFrame:
    """
    Expande cada compra parcelada em uma linha por parcela, com data de vencimento calculada.

    Regras:
    - Se o dia da compra <= dia de vencimento -> 1ª parcela vence neste mês.
    - Se o dia da compra >  dia de vencimento -> 1ª parcela vence no mês seguinte.
    """
    rows = []
    for _, row in df.iterrows():
        purchase_date = row["date"]
        n_parc = int(row["installments"])
        total_value = float(row["amount"])

        n_parc = max(n_parc, 1)
        parcela_value = total_value / n_parc

        if purchase_date.day <= due_day:
            first_due = purchase_date.replace(day=due_day)
        else:
            first_due = (purchase_date + relativedelta(months=1)).replace(day=due_day)

        for k in range(1, n_parc + 1):
            due_date = first_due + relativedelta(months=k - 1)

            rows.append({
                "category": row["category"],
                "purchase_date": purchase_date,
                "card_name": row["card_name"],
                "description": row["description"],
                "installment_no": k,
                "total_installments": n_parc,
                "installment_value": parcela_value,
                "due_date": due_date,
            })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out["due_date"] = pd.to_datetime(out["due_date"]).dt.date
    return out


def compute_card_summary(expanded: pd.DataFrame):
    """
    Retorna:
    - valor_fatura_mes: total de parcelas que vencem no mês atual
    - divida_ano_a_pagar: parcelas do ano atual com vencimento >= hoje
    - valor_pago_ano: parcelas do ano atual com vencimento < hoje
    """
    if expanded.empty:
        return 0.0, 0.0, 0.0

    today = date.today()
    current_year = today.year
    current_month = today.month

    mask_mes_atual = expanded["due_date"].apply(
        lambda d: d.year == current_year and d.month == current_month
    )
    valor_fatura_mes = expanded.loc[mask_mes_atual, "installment_value"].sum()

    mask_ano_atual = expanded["due_date"].apply(lambda d: d.year == current_year)

    mask_pago = mask_ano_atual & (expanded["due_date"] < today)
    valor_pago_ano = expanded.loc[mask_pago, "installment_value"].sum()

    mask_a_pagar = mask_ano_atual & (expanded["due_date"] >= today)
    divida_ano_a_pagar = expanded.loc[mask_a_pagar, "installment_value"].sum()

    return valor_fatura_mes, divida_ano_a_pagar, valor_pago_ano


def consolidar_dividas_ativas(expanded: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida parcelas em UMA LINHA por compra, informando:
      - total da compra
      - parcelas pagas
      - parcelas restantes
      - próximo vencimento
      - saldo a pagar

    Considera 'ativas' as compras com pelo menos UMA parcela com due_date >= hoje.
    """
    if expanded.empty:
        return pd.DataFrame()

    today = date.today()

    keys = [
        "card_name",
        "category",
        "purchase_date",
        "description",
        "total_installments",
        "installment_value",
    ]
    rows = []

    for _, g in expanded.groupby(keys, dropna=False):
        total_installments = int(g["total_installments"].iloc[0])
        parcela_value = float(g["installment_value"].iloc[0])

        dues = g.sort_values("installment_no")["due_date"].tolist()

        paid = sum(1 for d in dues if d < today)
        remaining = total_installments - paid

        if remaining <= 0:
            # já quitada, não entra como ativa
            continue

        next_due = min(d for d in dues if d >= today)

        total_value = total_installments * parcela_value
        remaining_value = remaining * parcela_value

        rows.append({
            "card_name": g["card_name"].iloc[0],
            "category": g["category"].iloc[0],
            "purchase_date": g["purchase_date"].iloc[0],
            "total_value": total_value,
            "installments_paid": paid,
            "installments_remaining": remaining,
            "next_due": next_due,
            "remaining_value": remaining_value,
            "description": g["description"].iloc[0],
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["purchase_date"] = out["purchase_date"].apply(lambda d: d.strftime("%d/%m/%Y"))
    out["next_due"] = out["next_due"].apply(lambda d: d.strftime("%d/%m/%Y"))

    out["total_value"] = out["total_value"].map(
        lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    out["remaining_value"] = out["remaining_value"].map(
        lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )

    out = out.rename(columns={
        "card_name": "Cartão",
        "category": "Categoria",
        "purchase_date": "Data da compra",
        "total_value": "Total da compra",
        "installments_paid": "Parcelas pagas",
        "installments_remaining": "Parcelas restantes",
        "next_due": "Próximo vencimento",
        "remaining_value": "Saldo a pagar",
        "description": "Descrição",
    })

    cols = [
        "Cartão",
        "Categoria",
        "Data da compra",
        "Total da compra",
        "Parcelas pagas",
        "Parcelas restantes",
        "Próximo vencimento",
        "Saldo a pagar",
        "Descrição",
    ]
    return out[cols]


# -------------------------------------------------------------------
# PÁGINA PRINCIPAL DO MÓDULO DE CARTÃO
# -------------------------------------------------------------------

def pagina_cartao(df: pd.DataFrame):
    """
    df vem do controle.py (já filtrado por user_id em load_data).
    Aqui só filtramos as despesas pagas com cartão e montamos o módulo.
    """
    st.markdown("### 💳 Módulo de Cartão de Crédito")

    if df.empty:
        st.info("Ainda não há lançamentos para este usuário.")
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date

    if "installments" not in df.columns:
        df["installments"] = 1
    if "card_name" not in df.columns:
        df["card_name"] = ""
    if "description" not in df.columns:
        df["description"] = ""

    df["installments"] = df["installments"].fillna(1).astype(int)
    df["amount"] = df["amount"].astype(float)

    # Apenas saídas pagas com cartão de crédito
    df_cartao = df[
        (df["type"] == "saida") &
        (df["payment_type"] == "Cartão de crédito")
    ].copy()

    if df_cartao.empty:
        st.info("Ainda não há despesas lançadas com cartão de crédito.")
        return

    # Configuração: dia de vencimento
    st.sidebar.markdown("### Configurações do cartão")
    due_day = st.sidebar.slider(
        "Dia de vencimento da fatura",
        min_value=1,
        max_value=28,
        value=5,
        help="Assumimos que todas as faturas vencem neste dia do mês.",
    )

    expanded = expand_installments(df_cartao, due_day)

    # -------------------------------------------------------------------
    # CARDS DE RESUMO
    # -------------------------------------------------------------------
    valor_fatura_mes, divida_ano_a_pagar, valor_pago_ano = compute_card_summary(expanded)

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Cartão a pagar no mês",
        f"R$ {valor_fatura_mes:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    )
    col2.metric(
        "Dívida do ano ainda a pagar",
        f"R$ {divida_ano_a_pagar:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    )
    col3.metric(
        "Valor já pago no ano",
        f"R$ {valor_pago_ano:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # GRÁFICO DE CATEGORIAS + PORCENTAGENS
    # -------------------------------------------------------------------
    st.subheader("Categorias mais gastas no cartão (ano atual)")

    current_year = date.today().year
    df_year = df_cartao[df_cartao["date"].apply(lambda d: d.year == current_year)]

    if not df_year.empty:
        cat_totais = (
            df_year.groupby("category")["amount"]
            .sum()
            .reset_index()
            .rename(columns={"amount": "total"})
            .sort_values("total", ascending=False)
        )

        total_geral = cat_totais["total"].sum()
        cat_totais["percentual"] = cat_totais["total"] / total_geral * 100

        chart_cat = (
            alt.Chart(cat_totais)
            .mark_bar(color="#FFA500") # laranja
            .encode(
                x=alt.X("category:N", title="Categoria"),
                y=alt.Y("total:Q", title="Valor (R$)"),
                tooltip=[
                    alt.Tooltip("category:N", title="Categoria"),
                    alt.Tooltip("total:Q", title="Total (R$)", format=",.2f"),
                    alt.Tooltip("percentual:Q", title="% do total", format=",.2f"),
                ],
            )
        )
        st.altair_chart(chart_cat, use_container_width=True)

        st.markdown("#### Participação de cada categoria no total de despesas com cartão")
        cat_view = cat_totais.copy()
        cat_view["total"] = cat_view["total"].map(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        cat_view["percentual"] = cat_view["percentual"].map(lambda v: f"{v:.2f}%")
        st.dataframe(cat_view, use_container_width=True)
    else:
        st.info("Não há compras no cartão no ano atual para gerar o gráfico por categoria.")

    st.markdown("---")

    # -------------------------------------------------------------------
    # HISTÓRICO ANUAL (por mês de vencimento)
    # -------------------------------------------------------------------
    st.subheader("Histórico anual de uso do cartão (por vencimento)")

    if not expanded.empty:
        this_year = date.today().year
        exp_year = expanded[expanded["due_date"].apply(lambda d: d.year == this_year)]

        if not exp_year.empty:
            exp_year["mes"] = exp_year["due_date"].apply(lambda d: d.month)
            mensal = (
                exp_year.groupby("mes")["installment_value"]
                .sum()
                .reindex(range(1, 13), fill_value=0)
                .reset_index()
                .rename(columns={"mes": "Mês", "installment_value": "Fatura"})
            )

            mensal["NomeMes"] = mensal["Mês"].map({
                1: "Jan",
                2: "Fev",
                3: "Mar",
                4: "Abr",
                5: "Mai",
                6: "Jun",
                7: "Jul",
                8: "Ago",
                9: "Set",
                10: "Out",
                11: "Nov",
                12: "Dez",
            })

            chart_hist = (
                alt.Chart(mensal)
                .mark_line(point=True)
                .encode(
                    x=alt.X("NomeMes:N", title="Mês"),
                    y=alt.Y("Fatura:Q", title="Valor (R$)"),
                    tooltip=[
                        alt.Tooltip("NomeMes:N", title="Mês"),
                        alt.Tooltip("Fatura:Q", title="Fatura (R$)", format=",.2f"),
                    ],
                )
            )
            st.altair_chart(chart_hist, use_container_width=True)
        else:
            st.info("Ainda não há parcelas com vencimento no ano atual.")
    else:
        st.info("Não há parcelas para montar o histórico anual.")

    st.markdown("---")

    # -------------------------------------------------------------------
    # TABELAS: DÍVIDAS ATIVAS x CONCLUÍDAS + FILTROS
    # -------------------------------------------------------------------
    st.subheader("Dívidas no cartão")

    if expanded.empty:
        st.info("Não há dívidas de cartão registradas.")
        return

    base = expanded.copy()

    # opções de cartão, categoria e ano (da data da compra)
    cartoes = sorted(base["card_name"].dropna().unique().tolist())
    categorias = sorted(base["category"].dropna().unique().tolist())
    anos = sorted({d.year for d in base["purchase_date"]})

    with st.form("filtros_dividas_cartao"):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)

        with col_f1:
            card_sel = st.selectbox(
                "Cartão",
                ["Todos"] + cartoes if cartoes else ["Todos"],
            )
        with col_f2:
            cat_sel = st.selectbox(
                "Categoria",
                ["Todas"] + categorias if categorias else ["Todas"],
            )
        with col_f3:
            ano_sel = st.selectbox(
                "Ano da compra",
                ["Todos"] + anos if anos else ["Todos"],
            )
        with col_f4:
            status_sel = st.selectbox(
                "Status",
                ["Todos", "Ativas", "Concluídas"],
            )

        texto_busca = st.text_input(
            "Buscar na descrição",
            value="",
            placeholder="Ex: mercado, passagem, viagem...",
        )

        aplicar = st.form_submit_button("Aplicar filtros")

    df_filt = base

    if card_sel != "Todos":
        df_filt = df_filt[df_filt["card_name"] == card_sel]

    if cat_sel != "Todas":
        df_filt = df_filt[df_filt["category"] == cat_sel]

    if ano_sel != "Todos":
        df_filt = df_filt[df_filt["purchase_date"].apply(lambda d: d.year == int(ano_sel))]

    if texto_busca:
        df_filt = df_filt[
            df_filt["description"].fillna("").str.contains(texto_busca, case=False, na=False)
        ]

    today = date.today()

    # ------------ NOVA LÓGICA PARA CONCLUÍDAS 100% QUITADAS ------------
    group_cols = [
        "card_name",
        "category",
        "purchase_date",
        "description",
        "total_installments",
        "installment_value",
    ]

    if not df_filt.empty:
        df_filt["purchase_group"] = df_filt[group_cols].apply(
            lambda r: tuple(r.values.tolist()),
            axis=1,
        )

        fully_paid_groups = set()
        for grp_key, g in df_filt.groupby("purchase_group", dropna=False):
            # Se a última parcela (maior due_date) já passou, a compra está 100% concluída
            if g["due_date"].max() < today:
                fully_paid_groups.add(grp_key)

        concluido = df_filt[
            (df_filt["due_date"] < today) &
            (df_filt["purchase_group"].isin(fully_paid_groups))
        ].copy()

        # removemos a coluna auxiliar para o restante do fluxo
        df_filt = df_filt.drop(columns=["purchase_group"])
    else:
        concluido = df_filt.copy()

    # Dívidas ativas consolidadas (1 linha por compra)
    df_ativas = consolidar_dividas_ativas(df_filt)

    if status_sel == "Ativas":
        mostrar_ativas = True
        mostrar_concluidas = False
    elif status_sel == "Concluídas":
        mostrar_ativas = False
        mostrar_concluidas = True
    else:
        mostrar_ativas = True
        mostrar_concluidas = True

    def format_table(df_tab: pd.DataFrame) -> pd.DataFrame:
        if df_tab.empty:
            return df_tab
        out = df_tab.copy()
        out["purchase_date"] = out["purchase_date"].apply(lambda d: d.strftime("%d/%m/%Y"))
        out["due_date"] = out["due_date"].apply(lambda d: d.strftime("%d/%m/%Y"))
        out["installment_value"] = out["installment_value"].map(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        out.rename(
            columns={
                "card_name": "Cartão",
                "category": "Categoria",
                "purchase_date": "Data da compra",
                "due_date": "Vencimento",
                "installment_no": "Parcela",
                "total_installments": "Total parcelas",
                "installment_value": "Valor parcela",
                "description": "Descrição",
            },
            inplace=True,
        )
        cols = [
            "Cartão",
            "Categoria",
            "Data da compra",
            "Vencimento",
            "Parcela",
            "Total parcelas",
            "Valor parcela",
            "Descrição",
        ]
        return out[cols]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Dívidas ativas (consolidadas)")
        if not mostrar_ativas:
            st.write("Filtrando apenas dívidas concluídas.")
        elif df_ativas.empty:
            st.write("✔️ Nenhuma dívida ativa encontrada com os filtros selecionados.")
        else:
            st.dataframe(df_ativas, use_container_width=True, height=350)

    with col_b:
        st.markdown("#### Dívidas concluídas (compras 100% quitadas)")
        if not mostrar_concluidas:
            st.write("Filtrando apenas dívidas ativas.")
        elif concluido.empty:
            st.write("Nenhuma compra 100% quitada encontrada com os filtros selecionados.")
        else:
            st.dataframe(format_table(concluido), use_container_width=True, height=350)

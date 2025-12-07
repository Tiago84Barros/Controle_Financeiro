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
            due_date = first_due + relativedelta(months=k-1)

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

    mask_mes_atual = (
        expanded["due_date"].apply(lambda d: d.year == current_year and d.month == current_month)
    )
    valor_fatura_mes = expanded.loc[mask_mes_atual, "installment_value"].sum()

    mask_ano_atual = expanded["due_date"].apply(lambda d: d.year == current_year)

    mask_pago = mask_ano_atual & (expanded["due_date"] < today)
    valor_pago_ano = expanded.loc[mask_pago, "installment_value"].sum()

    mask_a_pagar = mask_ano_atual & (expanded["due_date"] >= today)
    divida_ano_a_pagar = expanded.loc[mask_a_pagar, "installment_value"].sum()

    return valor_fatura_mes, divida_ano_a_pagar, valor_pago_ano


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

    # Normaliza tipos básicos
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

    # 🔴 CORREÇÃO AQUI:
    # Filtra só saídas pagas com cartão de crédito
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
        help="Assumimos que todas as faturas vencem neste dia do mês."
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
            .mark_bar()
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
                1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
                5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
                9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
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
    # TABELAS: DÍVIDAS ATIVAS x CONCLUÍDAS
    # -------------------------------------------------------------------
    st.subheader("Dívidas no cartão")

    if expanded.empty:
        st.info("Não há dívidas de cartão registradas.")
        return

    today = date.today()
    ativos = expanded[expanded["due_date"] >= today].copy()
    concluido = expanded[expanded["due_date"] < today].copy()

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
            "Cartão", "Categoria", "Data da compra", "Vencimento",
            "Parcela", "Total parcelas", "Valor parcela", "Descrição",
        ]
        return out[cols]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("#### Dívidas ativas (parcelas futuras)")
        if ativos.empty:
            st.write("✔️ Nenhuma parcela futura em aberto.")
        else:
            st.dataframe(format_table(ativos), use_container_width=True, height=350)

    with col_b:
        st.markdown("#### Dívidas concluídas (parcelas já pagas)")
        if concluido.empty:
            st.write("Ainda não há parcelas concluídas no histórico.")
        else:
            st.dataframe(format_table(concluido), use_container_width=True, height=350)

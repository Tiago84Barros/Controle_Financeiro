import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
from dateutil.relativedelta import relativedelta
import psycopg2


# -------------------------------------------------------------------
# CONEXÃO COM BANCO / UPDATE DE TRANSAÇÕES
# -------------------------------------------------------------------

def get_connection():
    """
    Abre conexão com o banco (Supabase/Postgres) usando st.secrets,
    no mesmo padrão do controle.py.
    """
    dsn = st.secrets["supabase_db"]["url"]
    conn = psycopg2.connect(dsn, sslmode="require")
    return conn


def update_transaction_fields(
    transaction_id: int,
    new_category: str,
    new_card_name: str,
    new_description: str,
):
    """
    Atualiza apenas campos de alto nível da transação original:
    - categoria
    - card_name
    - descrição
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE transactions
           SET category = %s,
               card_name = %s,
               description = %s
         WHERE id = %s
        """,
        (new_category, new_card_name, new_description, transaction_id),
    )
    conn.commit()
    cur.close()
    conn.close()


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

            rows.append(
                {
                    "transaction_id": row["id"],
                    "category": row["category"],
                    "purchase_date": purchase_date,
                    "card_name": row["card_name"],
                    "description": row["description"],
                    "installment_no": k,
                    "total_installments": n_parc,
                    "installment_value": parcela_value,
                    "due_date": due_date,
                }
            )

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


def build_purchase_overview(expanded: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida por COMPRA (transaction_id), calculando:
      - status: 'ativa' ou 'concluida'
      - total da compra
      - parcelas pagas / restantes
      - próximo vencimento
      - saldo a pagar
    """
    if expanded.empty:
        return pd.DataFrame()

    today = date.today()
    rows = []

    for tid, g in expanded.groupby("transaction_id", dropna=False):
        g = g.sort_values("installment_no")
        total_installments = int(g["total_installments"].iloc[0])
        parcela_value = float(g["installment_value"].iloc[0])
        dues = g["due_date"].tolist()

        paid = sum(1 for d in dues if d < today)
        remaining = total_installments - paid
        last_due = max(dues)

        if remaining <= 0 and last_due < today:
            status = "concluida"
        else:
            status = "ativa"

        next_due = None
        if remaining > 0:
            future_dues = [d for d in dues if d >= today]
            next_due = min(future_dues) if future_dues else None

        total_value = total_installments * parcela_value
        remaining_value = max(0, remaining * parcela_value)

        rows.append(
            {
                "transaction_id": tid,
                "card_name": g["card_name"].iloc[0],
                "category": g["category"].iloc[0],
                "purchase_date": g["purchase_date"].iloc[0],
                "total_installments": total_installments,
                "installments_paid": paid,
                "installments_remaining": remaining,
                "total_value": total_value,
                "remaining_value": remaining_value,
                "next_due": next_due,
                "description": g["description"].iloc[0],
                "status": status,
            }
        )

    return pd.DataFrame(rows)


def format_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
        format_brl(valor_fatura_mes),
    )
    col2.metric(
        "Dívida do ano ainda a pagar",
        format_brl(divida_ano_a_pagar),
    )
    col3.metric(
        "Valor já pago no ano",
        format_brl(valor_pago_ano),
    )

    st.markdown("---")

    # -------------------------------------------------------------------
    # GRÁFICO DE CATEGORIAS + PORCENTAGENS (LARANJA)
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
            .mark_bar(color="#FFA500")  # laranja
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
        cat_view["total"] = cat_view["total"].map(format_brl)
        cat_view["percentual"] = cat_view["percentual"].map(lambda v: f"{v:.2f}%")
        st.dataframe(cat_view, use_container_width=True)
    else:
        st.info("Não há compras no cartão no ano atual para gerar o gráfico por categoria.")

    st.markdown("---")

    # -------------------------------------------------------------------
    # HISTÓRICO ANUAL (por mês de vencimento) - MESES EM ORDEM
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

            mensal["NomeMes"] = mensal["Mês"].map(
                {
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
                }
            )

            chart_hist = (
                alt.Chart(mensal)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "NomeMes:N",
                        title="Mês",
                        sort=[
                            "Jan",
                            "Fev",
                            "Mar",
                            "Abr",
                            "Mai",
                            "Jun",
                            "Jul",
                            "Ago",
                            "Set",
                            "Out",
                            "Nov",
                            "Dez",
                        ],
                    ),
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
    # VISÃO CONSOLIDADA POR COMPRA + FILTROS + EDIÇÃO SOB DEMANDA
    # -------------------------------------------------------------------
    st.subheader("Dívidas no cartão")

    if expanded.empty:
        st.info("Não há dívidas de cartão registradas.")
        return

    compras = build_purchase_overview(expanded)

    if compras.empty:
        st.info("Nenhuma compra com cartão encontrada.")
        return

    # -------------------------
    # Filtros
    # -------------------------
    cartoes = sorted(compras["card_name"].dropna().unique().tolist())
    categorias = sorted(compras["category"].dropna().unique().tolist())
    anos = sorted({d.year for d in compras["purchase_date"]})

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

    compras_filt = compras.copy()

    if card_sel != "Todos":
        compras_filt = compras_filt[compras_filt["card_name"] == card_sel]

    if cat_sel != "Todas":
        compras_filt = compras_filt[compras_filt["category"] == cat_sel]

    if ano_sel != "Todos":
        compras_filt = compras_filt[
            compras_filt["purchase_date"].apply(lambda d: d.year == int(ano_sel))
        ]

    if texto_busca:
        compras_filt = compras_filt[
            compras_filt["description"].fillna("").str.contains(texto_busca, case=False, na=False)
        ]

    # Separa ativas e concluídas (100% pagas)
    df_ativas = compras_filt[compras_filt["status"] == "ativa"].copy()
    df_concluidas = compras_filt[compras_filt["status"] == "concluida"].copy()

    if status_sel == "Ativas":
        mostrar_ativas = True
        mostrar_concluidas = False
    elif status_sel == "Concluídas":
        mostrar_ativas = False
        mostrar_concluidas = True
    else:
        mostrar_ativas = True
        mostrar_concluidas = True

    col_a, col_b = st.columns(2)

    # -------------------------------------------------------------------
    # TABELA: DÍVIDAS ATIVAS (visualização + edição sob demanda)
    # -------------------------------------------------------------------
    with col_a:
        st.markdown("#### Dívidas ativas (consolidadas)")

        if not mostrar_ativas:
            st.write("Filtrando apenas dívidas concluídas.")
        elif df_ativas.empty:
            st.write("✔️ Nenhuma dívida ativa encontrada com os filtros selecionados.")
        else:
            df_view_ativas = df_ativas.copy()
            df_view_ativas["Data da compra"] = df_view_ativas["purchase_date"].apply(
                lambda d: d.strftime("%d/%m/%Y")
            )
            df_view_ativas["Próximo vencimento"] = df_view_ativas["next_due"].apply(
                lambda d: d.strftime("%d/%m/%Y") if pd.notnull(d) else "-"
            )
            df_view_ativas["Total da compra"] = df_view_ativas["total_value"].map(format_brl)
            df_view_ativas["Saldo a pagar"] = df_view_ativas["remaining_value"].map(format_brl)

            df_view_ativas = df_view_ativas.rename(
                columns={
                    "transaction_id": "ID",
                    "card_name": "Cartão",
                    "category": "Categoria",
                    "installments_paid": "Parcelas pagas",
                    "installments_remaining": "Parcelas restantes",
                    "description": "Descrição",
                }
            )

            df_view_ativas = df_view_ativas[
                [
                    "ID",
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
            ]

            habilitar_edicao_ativas = st.checkbox(
                "Habilitar edição das dívidas ativas",
                key="chk_editar_ativas",
            )

            if not habilitar_edicao_ativas:
                # Esconde ID e índice na visualização
                df_view_ativas_sem_id = df_view_ativas.drop(columns=["ID"])
                st.dataframe(df_view_ativas_sem_id, use_container_width=True, height=350, hide_index=True,)
            else:
                edited_ativas = st.data_editor(
                    df_view_ativas,
                    num_rows="fixed",
                    key="editor_dividas_ativas",
                    hide_index=True,
                    column_config={
                        "ID": st.column_config.NumberColumn("ID", disabled=True),
                        "Total da compra": st.column_config.TextColumn(disabled=True),
                        "Parcelas pagas": st.column_config.NumberColumn(disabled=True),
                        "Parcelas restantes": st.column_config.NumberColumn(disabled=True),
                        "Próximo vencimento": st.column_config.TextColumn(disabled=True),
                        "Saldo a pagar": st.column_config.TextColumn(disabled=True),
                        # "Cartão", "Categoria" e "Descrição" ficam editáveis
                    },
                )

                if st.button("Salvar alterações (ativas)"):
                    base = df_view_ativas.set_index("ID")
                    novo = edited_ativas.set_index("ID")

                    alteracoes = 0
                    for idx in novo.index:
                        row_old = base.loc[idx]
                        row_new = novo.loc[idx]

                        if (
                            row_old["Cartão"] != row_new["Cartão"]
                            or row_old["Categoria"] != row_new["Categoria"]
                            or row_old["Descrição"] != row_new["Descrição"]
                        ):
                            update_transaction_fields(
                                transaction_id=int(idx),
                                new_category=row_new["Categoria"],
                                new_card_name=row_new["Cartão"],
                                new_description=row_new["Descrição"],
                            )
                            alteracoes += 1

                    if alteracoes > 0:
                        st.success(f"{alteracoes} compra(s) ativa(s) atualizada(s) com sucesso.")
                    else:
                        st.info("Nenhuma alteração detectada nas dívidas ativas.")

    # -------------------------------------------------------------------
    # TABELA: DÍVIDAS CONCLUÍDAS (visualização + edição sob demanda)
    # -------------------------------------------------------------------
    with col_b:
        st.markdown("#### Dívidas concluídas (compras 100% quitadas)")

        if not mostrar_concluidas:
            st.write("Filtrando apenas dívidas ativas.")
        elif df_concluidas.empty:
            st.write("Nenhuma compra 100% quitada encontrada com os filtros selecionados.")
        else:
            df_view_conc = df_concluidas.copy()
            df_view_conc["Data da compra"] = df_view_conc["purchase_date"].apply(
                lambda d: d.strftime("%d/%m/%Y")
            )
            df_view_conc["Total da compra"] = df_view_conc["total_value"].map(format_brl)

            df_view_conc = df_view_conc.rename(
                columns={
                    "transaction_id": "ID",
                    "card_name": "Cartão",
                    "category": "Categoria",
                    "total_installments": "Parcelas pagas",
                    "description": "Descrição",
                }
            )

            df_view_conc = df_view_conc[
                [
                    "ID",
                    "Cartão",
                    "Categoria",
                    "Data da compra",
                    "Total da compra",
                    "Parcelas pagas",
                    "Descrição",
                ]
            ]

            habilitar_edicao_concluidas = st.checkbox(
                "Habilitar edição das dívidas concluídas",
                key="chk_editar_concluidas",
            )

            if not habilitar_edicao_concluidas:
                # Esconde ID e índice na visualização
                df_view_conc_sem_id = df_view_conc.drop(columns=["ID"])
                st.dataframe(df_view_conc_sem_id, use_container_width=True, height=350, hide_index=True,)
            else:
                edited_conc = st.data_editor(
                    df_view_conc,
                    num_rows="fixed",
                    key="editor_dividas_concluidas",
                    hide_index=True,
                    column_config={
                        "ID": st.column_config.NumberColumn("ID", disabled=True),
                        "Total da compra": st.column_config.TextColumn(disabled=True),
                        "Parcelas pagas": st.column_config.NumberColumn(disabled=True),
                        "Data da compra": st.column_config.TextColumn(disabled=True),
                        # "Cartão", "Categoria" e "Descrição" editáveis
                    },
                )

                if st.button("Salvar alterações (concluídas)"):
                    base_c = df_view_conc.set_index("ID")
                    novo_c = edited_conc.set_index("ID")

                    alteracoes_c = 0
                    for idx in novo_c.index:
                        row_old = base_c.loc[idx]
                        row_new = novo_c.loc[idx]

                        if (
                            row_old["Cartão"] != row_new["Cartão"]
                            or row_old["Categoria"] != row_new["Categoria"]
                            or row_old["Descrição"] != row_new["Descrição"]
                        ):
                            update_transaction_fields(
                                transaction_id=int(idx),
                                new_category=row_new["Categoria"],
                                new_card_name=row_new["Cartão"],
                                new_description=row_new["Descrição"],
                            )
                            alteracoes_c += 1

                    if alteracoes_c > 0:
                        st.success(f"{alteracoes_c} compra(s) concluída(s) atualizada(s) com sucesso.")
                    else:
                        st.info("Nenhuma alteração detectada nas dívidas concluídas.")

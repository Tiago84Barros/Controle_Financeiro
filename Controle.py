import streamlit as st
import psycopg2
from datetime import date
import altair as alt
from dateutil.relativedelta import relativedelta
import pandas as pd

from Consulta_Tabelas import pagina_consulta_tabelas


st.set_page_config(
    page_title="Controle Financeiro",
    page_icon="💰",
)

st.markdown(
    """
    <link rel="manifest" href="manifes.json">
    """,
    unsafe_allow_html=True
)

DB_PATH = "finance.db"

# ---------- Banco de Dados ----------

def get_connection():
    dsn = st.secrets["supabase_db"]["url"]
    conn = psycopg2.connect(dsn, sslmode="require")
    return conn


def init_db():
    # Como já criamos a tabela no Supabase,
    # aqui apenas testamos a conexão
    conn = get_connection()
    conn.close()

def insert_transaction(t_type, category, d, amount, payment_type, card_name, installments, description):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions
        (type, category, date, amount, payment_type, card_name, installments, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (t_type, category, d, amount, payment_type, card_name, installments, description),
    )
    conn.commit()
    conn.close()


def load_data():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC", conn)
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

# ---------- Lógica de Resumo ----------

def get_month_range(target_date=None):
    if target_date is None:
        target_date = date.today()
    first_day = target_date.replace(day=1)
    next_month = first_day + relativedelta(months=1)
    last_day = next_month - relativedelta(days=1)
    return first_day, last_day

def compute_summary(df, ref_date):
    if df.empty:
        return {
            "total_entrada": 0.0,
            "total_saida": 0.0,
            "total_investimento": 0.0,
            "saldo": 0.0,
            "perc_comprometido": 0.0,
        }, pd.DataFrame(), pd.DataFrame()

    first_day, last_day = get_month_range(ref_date)
    mask_month = (df["date"] >= first_day) & (df["date"] <= last_day)
    df_month = df[mask_month].copy()

    total_entrada = df_month.loc[df_month["type"] == "entrada", "amount"].sum()
    total_saida = df_month.loc[df_month["type"] == "saida", "amount"].sum()
    total_investimento = df_month.loc[df_month["type"] == "investimento", "amount"].sum()

    # 🔹 saldo líquido: entradas - saídas - investimentos
    saldo = total_entrada - total_saida - total_investimento

    # 🔹 renda comprometida: saídas + investimentos
    comprometido = total_saida + total_investimento
    perc_comprometido = (comprometido / total_entrada * 100) if total_entrada > 0 else 0

    # Despesas por categoria no mês (só saídas, como antes)
    df_cat = (
        df_month[df_month["type"] == "saida"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
    )

    # Histórico últimos 6 meses (entrada/saida/investimento)
    six_months_ago = first_day - relativedelta(months=5)
    mask_hist = (df["date"] >= six_months_ago) & (df["date"] <= last_day)
    df_hist = df[mask_hist].copy()
    if not df_hist.empty:
        df_hist["ym"] = df_hist["date"].apply(lambda d: d.replace(day=1))
        df_hist = df_hist.groupby(["ym", "type"])["amount"].sum().reset_index()
        df_hist_pivot = df_hist.pivot(index="ym", columns="type", values="amount").fillna(0)
        df_hist_pivot = df_hist_pivot.rename(columns={"entrada": "Receitas", "saida": "Despesas"})
        df_hist_pivot = df_hist_pivot.sort_index()
    else:
        df_hist_pivot = pd.DataFrame()

    resumo = {
        "total_entrada": float(total_entrada),
        "total_saida": float(total_saida),
        "total_investimento": float(total_investimento),
        "saldo": float(saldo),
        "perc_comprometido": float(round(perc_comprometido, 1)),
    }

    return resumo, df_cat, df_hist_pivot

# ---------- Formatação BRL ----------

def format_brl(value: float) -> str:
    """
    Formata número no padrão brasileiro: R$ 23.306,10
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_percent(value: float) -> str:
    """
    Formata percentual no padrão brasileiro: 23,4%
    """
    return f"{value:,.1f}%".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_brl_to_float(valor_str: str) -> float:
    """
    Converte string em formato brasileiro (23.306,10) para float (23306.10).
    Aceita também 'R$ 23.306,10', espaços etc.
    """
    if not valor_str:
        return 0.0
    s = valor_str.strip()
    s = s.replace("R$", "").strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0



# ---------- Estilo visual ----------

def apply_custom_style():
    st.markdown(
        """
        <style>
        /* Fundo geral */
        .stApp {
            background: radial-gradient(circle at top left, #0f172a 0, #020617 45%, #020617 100%);
            color: #e5e7eb;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        /* Header */
        .cf-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
            padding: 0.5rem 0.25rem 0.75rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.3);
        }
        .cf-title {
            font-size: 1.6rem;
            font-weight: 600;
            margin: 0;
        }
        .cf-subtitle {
            font-size: 0.9rem;
            color: #9ca3af;
            margin-top: 0.15rem;
        }
        .cf-subtitle strong {
            color: #e5e7eb;
        }
        .cf-pill {
            font-size: 0.8rem;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            background: rgba(148, 163, 184, 0.22);
            color: #e5e7eb;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }

        /* Cards de resumo */
        .cf-card {
            border-radius: 0.9rem;
            padding: 0.9rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.25);
            background: radial-gradient(circle at top left, rgba(148, 163, 184, 0.15), rgba(15, 23, 42, 0.9));
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(8px);
        }
        .cf-card-label {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #9ca3af;
            margin-bottom: 0.3rem;
        }
        .cf-card-value {
            font-size: 1.45rem;
            font-weight: 600;
        }
        .cf-card-extra {
            font-size: 0.75rem;
            color: #9ca3af;
            margin-top: 0.25rem;
        }
        .cf-card-income .cf-card-value {
            color: #4ade80;
        }
        .cf-card-expense .cf-card-value {
            color: #f97373;
        }
        .cf-card-balance-positive .cf-card-value {
            color: #22c55e;
        }
        .cf-card-balance-negative .cf-card-value {
            color: #fb7185;
        }
        .cf-card-ratio .cf-card-value {
            color: #60a5fa;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ---------- App Streamlit ----------

def main():
    st.set_page_config(
        page_title="Dashboard Financeiro",
        page_icon="💰",
        layout="wide",
    )

    apply_custom_style()
    init_db()

    # --- Navegação entre páginas ---
    pagina = st.sidebar.radio(
        "Navegação",
        ["Dashboard", "Análises", "Consulta de Tabelas"],
        horizontal=False
    )

    # 👉 Se for consulta, chama o módulo novo e sai
    if pagina == "Consulta de Tabelas":
        pagina_consulta_tabelas(get_connection)
        return

    # Carrega dados uma única vez (para Dashboard e Análises)
    df = load_data()

    # 👉 Se for análises, chama render_analises e sai
    if pagina == "Análises":
        render_analises(df)
        return

   
    # --- SIDEBAR DO DASHBOARD ---
    with st.sidebar:
        st.header("Filtros")
        today = date.today()
        ref_date = st.date_input(
            "Mês de referência",
            value=today,
            format="DD/MM/YYYY"
        )
        st.markdown("---")
    
        # Categorias pré-definidas
        income_categories = [
            "Salário",
            "Renda Extra",
            "Dividendos",
            "Reembolso",
            "Outros"
        ]
    
        expense_categories = [
            "Mercado",
            "Condomínio",
            "Luz",
            "Internet",
            "Transporte",
            "Combustível",
            "Saúde",
            "Despesas Domésticas",
            "Lazer",
            "Assinaturas",
            "Educação",
            "Restaurante",
            "Financiamento",
            "Pagamento de Cartão",
            "Outros"
        ]
    
        investment_categories = [
            "Renda Fixa",
            "Renda Variável",
            "Exterior",
            "Reserva de Despesa",
            "Outra"
        ]
    
        st.header("Novo lançamento")
    
        # 🔹 Tipo agora tem 3 opções
        t_type = st.radio("Tipo", ["entrada", "saida", "investimento"], horizontal=True)
    
        with st.form("novo_lancamento", clear_on_submit=True):
    
            # 🔹 Seleção dinâmica de categorias
            if t_type == "entrada":
                cat_choice = st.selectbox("Categoria", income_categories + ["Outra"])
            elif t_type == "saida":
                cat_choice = st.selectbox("Categoria", expense_categories + ["Outra"])
            else:  # investimento
                cat_choice = st.selectbox("Categoria", investment_categories)
    
            # Se escolher "Outra", mostra campo manual
            if cat_choice == "Outra":
                category = st.text_input("Categoria personalizada")
            else:
                category = cat_choice
    
            # 🔹 Data no formato BR
            d = st.date_input(
                "Data",
                value=today,
                format="DD/MM/YYYY",
                key="data_lanc"
            )
    
            # 🔹 Campo Valor (como string BR)
            valor_str = st.text_input("Valor (R$)", value="", placeholder="0,00")
    
            # 🔹 Forma de pagamento (só aparece para saída e entrada)
            if t_type in ["entrada", "saida"]:
                payment_type = st.selectbox(
                    "Forma de pagamento",
                    ["Conta", "Cartão de crédito", "Dinheiro", "Pix"]
                )
            else:
                payment_type = "Conta"   # investimento sai sempre da conta
    
            card_name = ""
            installments = 1
    
            if payment_type == "Cartão de crédito":
                card_name = st.text_input("Nome do cartão")
                installments = st.number_input("Parcelas", min_value=1, value=1, step=1)
    
            description = st.text_area("Descrição (opcional)")
    
            submitted = st.form_submit_button("Salvar lançamento")
    
            if submitted:
                amount = parse_brl_to_float(valor_str)
    
                if amount > 0 and category.strip():
                    insert_transaction(
                        t_type,
                        category.strip(),
                        d.isoformat(),
                        float(amount),
                        payment_type,
                        card_name.strip() or None,
                        int(installments),
                        description.strip(),
                    )
                    st.success("Lançamento salvo com sucesso!")
                else:
                    st.error("Preencha categoria e valor maior que zero.")

 
    # --- DADOS ---
    df = load_data()
       
    resumo, df_cat, df_hist = compute_summary(df, ref_date)

    # --- HEADER NOVO ---
    st.markdown(
        f"""
        <div class="cf-header">
            <div>
                <h1 class="cf-title">💰 Controle Financeiro</h1>
                <p class="cf-subtitle">
                    Visão geral de <strong>{ref_date.month:02d}/{ref_date.year}</strong> • acompanhe renda, despesas e saldo em tempo real
                </p>
            </div>
            <div>
                <span class="cf-pill">
                     Mês atual: {ref_date.strftime("%d/%m/%Y")}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- CARDS DE RESUMO ---
    col1, col2, col3, col4 = st.columns(4)

    col1.markdown(
        f"""
        <div class="cf-card cf-card-income">
            <div class="cf-card-label">Renda do mês</div>
            <div class="cf-card-value">{format_brl(resumo['total_entrada'])}</div>
            <div class="cf-card-extra">Somatório de todas as entradas no período selecionado.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    col2.markdown(
        f"""
        <div class="cf-card cf-card-expense">
            <div class="cf-card-label">Despesas do mês</div>
            <div class="cf-card-value">{format_brl(resumo['total_saida'])}</div>
            <div class="cf-card-extra">Somatório de todas as saídas no período.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    saldo_class = "cf-card-balance-positive" if resumo["saldo"] >= 0 else "cf-card-balance-negative"
    if resumo["saldo"] >= 0:
        saldo_label_extra = (
            f"Sobrou dinheiro este mês. 👏<br/>"
            f"Investido no mês: {format_brl(resumo['total_investimento'])}"
        )
    else:
        saldo_label_extra = (
            f"Atenção: você gastou + investiu mais do que ganhou.<br/>"
            f"Investido no mês: {format_brl(resumo['total_investimento'])}"
        )
    
    col3.markdown(
        f"""
        <div class="cf-card {saldo_class}">
            <div class="cf-card-label">Saldo líquido do mês</div>
            <div class="cf-card-value">{format_brl(resumo['saldo'])}</div>
            <div class="cf-card-extra">{saldo_label_extra}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    
    col4.markdown(
        f"""
        <div class="cf-card cf-card-ratio">
            <div class="cf-card-label">Renda comprometida</div>
            <div class="cf-card-value">{format_percent(resumo['perc_comprometido'])}</div>
            <div class="cf-card-extra">
                Considera despesas + investimentos em relação à renda do mês.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ---------- GRÁFICOS ----------
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.markdown("#### Gastos por categoria (mês)")
        if not df_cat.empty:
            # -------- Gráfico em barras (vermelho) --------
            df_cat_chart = df_cat.set_index("category")
    
            import altair as alt
    
            chart = (
                alt.Chart(df_cat_chart.reset_index())
                .mark_bar(color="#ff4d4d")  # barras vermelhas
                .encode(
                    x=alt.X("category:N", title="Categoria", sort="-y"),
                    y=alt.Y("amount:Q", title="Valor (R$)")
                )
                .properties(height=350)
            )
    
            st.altair_chart(chart, use_container_width=True)
    
            # -------- Tabela formatada com % da renda --------
            df_cat_fmt = df_cat.copy()
    
            # calcula percentual da renda para cada categoria
            if resumo["total_entrada"] > 0:
                df_cat_fmt["percent_renda"] = (df_cat_fmt["amount"] / resumo["total_entrada"]) * 100
            else:
                df_cat_fmt["percent_renda"] = 0.0
    
            # renomeia colunas para exibição
            df_cat_fmt = df_cat_fmt.rename(
                columns={
                    "category": "Categoria",
                    "amount": "Valor (R$)",
                    "percent_renda": "% da renda",
                }
            )
    
            # formata valores em R$ (pt-BR)
            df_cat_fmt["Valor (R$)"] = df_cat_fmt["Valor (R$)"].apply(
                lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
    
            # formata percentual usando a função que você já tem
            df_cat_fmt["% da renda"] = df_cat_fmt["% da renda"].apply(format_percent)
    
            # remove índice numérico e reinicia para não aparecer a coluna de números
            df_cat_fmt = df_cat_fmt.reset_index(drop=True)
    
            st.dataframe(df_cat_fmt, use_container_width=True, hide_index=True)
    
        else:
            st.info("Não há despesas cadastradas neste mês.")

        
    with col_g2:
        st.markdown("#### Histórico de 6 meses (Receitas x Despesas x Investimentos)")
        if not df_hist.empty:
            # df_hist vem como pivot (index = ym, colunas = tipos)
            df_hist_chart = df_hist.copy()
    
            # Garante datetime e cria label de mês
            df_hist_chart.index = pd.to_datetime(df_hist_chart.index)
            df_hist_chart["mes"] = df_hist_chart.index.strftime("%m/%y")
    
            # Renomeia a coluna de investimento para um nome mais amigável
            if "investimento" in df_hist_chart.columns:
                df_hist_chart = df_hist_chart.rename(columns={"investimento": "Investimentos"})
    
            # Deixa em formato longo para o Altair
            df_long = df_hist_chart.melt(
                id_vars="mes",
                var_name="Tipo",
                value_name="Valor"
            )
    
            # Gráfico de linhas com cores específicas
            chart_hist = (
                alt.Chart(df_long)
                .mark_line(point=True)
                .encode(
                    x=alt.X("mes:N", title="Mês"),
                    y=alt.Y("Valor:Q", title="Valor (R$)"),
                    color=alt.Color(
                        "Tipo:N",
                        title="Tipo",
                        scale=alt.Scale(
                            domain=["Receitas", "Investimentos", "Despesas"],
                            range=["#3b82f6", "#22c55e", "#ef4444"],  # azul, verde, vermelho
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip("mes:N", title="Mês"),
                        alt.Tooltip("Tipo:N", title="Tipo"),
                        alt.Tooltip("Valor:Q", title="Valor", format=",.2f"),
                    ],
                )
                .properties(
                    width="container",
                    height=320,
                )
            )
    
            st.altair_chart(chart_hist, use_container_width=True)
    
            # --- Tabela formatada em BRL ---
            df_hist_tab = df_hist_chart.set_index("mes").drop(columns=[], errors="ignore")
            df_hist_fmt = df_hist_tab.copy()
            for col in df_hist_fmt.columns:
                df_hist_fmt[col] = df_hist_fmt[col].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
    
            df_hist_fmt = df_hist_fmt.rename_axis("Mês").reset_index()
            st.dataframe(df_hist_fmt, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para histórico.")

            
        st.markdown("---")

    # ---------- ÚLTIMOS LANÇAMENTOS ----------
    st.markdown("### Últimos lançamentos")

    if not df.empty:
        # pega os 20 últimos
        # 🔹 Ordem personalizada para o tipo:
        # entrada → investimento → saída
        type_order = {
            "entrada": 0,
            "investimento": 1,
            "saida": 2,
        }

        df_sorted = df.copy()
        df_sorted["type_order"] = df_sorted["type"].map(type_order).fillna(99)

        # 🔹 Ordenação final:
        # 1) Tipo (ordem personalizada)
        # 2) Categoria (A → Z)
        # 3) Data (mais recente primeiro)
        df_sorted = df_sorted.sort_values(
            by=["type_order", "category", "date"],
            ascending=[True, True, False],
        ).head(20)

        # remove coluna auxiliar
        df_sorted = df_sorted.drop(columns=["type_order"])

        # Tabela para visualização (read-only), com data e valor formatados
        df_view = df_sorted.copy()
        df_view["date"] = df_view["date"].apply(lambda d: d.strftime("%d/%m/%Y"))

        # renomeia colunas para exibição
        df_view = df_view.rename(
            columns={
                "type": "Tipo",
                "category": "Categoria",
                "date": "Data",
                "amount": "Valor (R$)",
                "payment_type": "Forma",
                "card_name": "Cartão",
                "installments": "Parcelas",
                "description": "Descrição",
            }
        )

        # formata o valor em R$
        df_view["Valor (R$)"] = df_view["Valor (R$)"].apply(
            lambda v: f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        # 🔹 escolhe explicitamente as colunas e ordem:
        df_view = df_view[
            ["Tipo", "Categoria", "Data", "Valor (R$)", "Forma", "Cartão", "Parcelas", "Descrição"]
        ]

        edit_mode = st.checkbox("Habilitar edição dos últimos lançamentos")

        if not edit_mode:
            # modo somente leitura, sem índice numérico
            st.dataframe(df_view, use_container_width=True, hide_index=True)
        else:
            st.info("Edite as linhas desejadas e clique em **Salvar alterações** para gravar no banco.")

            # DataFrame para edição (mantém valores numéricos e datas nativas)
            df_edit = df_sorted[
                ["id", "type", "category", "date", "amount", "payment_type", "card_name", "installments", "description"]
            ].copy()
            
            df_edit = df_edit.rename(
                columns={
                    "id": "ID",
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



            edited_df = st.data_editor(
                df_edit,
                num_rows="fixed",
                hide_index=True,
                key="editor_ultimos",
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True),
                    "Data": st.column_config.DateColumn("Data"),
                    "Valor": st.column_config.NumberColumn("Valor", step=10.0, format="%.2f"),
                    "Parcelas": st.column_config.NumberColumn("Parcelas", step=1),
                },
            )

            if st.button("Salvar alterações"):
                # renomeia de volta para nomes do banco
                to_update = edited_df.rename(
                    columns={
                        "ID": "id",
                        "Tipo": "type",
                        "Categoria": "category",
                        "Data": "date",
                        "Valor": "amount",
                        "Forma": "payment_type",
                        "Cartão": "card_name",
                        "Parcelas": "installments",
                        "Descrição": "description",
                    }
                ).copy()

                # converte tipos
                to_update["date"] = pd.to_datetime(to_update["date"]).dt.date.apply(lambda d: d.isoformat())
                to_update["amount"] = to_update["amount"].astype(float)
                to_update["installments"] = to_update["installments"].astype(int)

                conn = get_connection()
                cur = conn.cursor()
                for _, row in to_update.iterrows():
                    cur.execute(
                        """
                        UPDATE transactions
                        SET type = %s, category = %s, date = %s, amount = %s,
                            payment_type = %s, card_name = %s, installments = %s, description = %s
                        WHERE id = %s
                        """,
                        (
                            row["type"],
                            row["category"],
                            row["date"],
                            row["amount"],
                            row["payment_type"],
                            row.get("card_name"),
                            row["installments"],
                            row.get("description"),
                            int(row["id"]),
                        ),
                    )
                conn.commit()
                conn.close()

                st.success("Alterações salvas com sucesso!")
                st.rerun()
    else:
        st.info("Nenhum lançamento cadastrado ainda.")


# __________________________________________________________________________________________________________________________________________________________

def render_analises(df):

    st.title("📊 Análises Financeiras")
    st.markdown("Exploração avançada dos seus dados financeiros.")

    if df.empty:
        st.warning("Nenhum dado disponível para análise.")
        return

    # -------------------------
    # 1️⃣ COMPARATIVO ANO vs ANO
    # -------------------------
    st.subheader("📅 Comparativo Ano a Ano")

    df['year'] = pd.to_datetime(df['date']).dt.year

    df_yoy = df.groupby(['year', 'type'])['amount'].sum().reset_index()

    tabela_yoy = df_yoy.pivot(index="year", columns="type", values="amount").fillna(0)
    tabela_yoy = tabela_yoy.rename(columns={
        "entrada": "Receitas",
        "saida": "Despesas",
        "investimento": "Investimentos"
    })

    # Formatação moeda
    tabela_fmt = tabela_yoy.applymap(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.dataframe(tabela_fmt, use_container_width=True)

   # Gráfico YOY (agrupado e responsivo)
    chart_yoy = (
        alt.Chart(df_yoy)
        .mark_bar()
        .encode(
            x=alt.X("year:N", title="Ano"),
            y=alt.Y("amount:Q", title="Valor (R$)"),
            color=alt.Color("type:N", title="Tipo"),
            tooltip=["year:N", "type:N", "amount:Q"],
        )
        .properties(
            width="container",   # ocupa a largura disponível
            height=320
        )
    )
    
    st.altair_chart(chart_yoy, use_container_width=True)


    st.markdown("---")

    # -----------------------------------
    # 2️⃣ DESPESAS POR FORMA DE PAGAMENTO
    # -----------------------------------
    st.subheader("💳 Despesas por forma de pagamento")

    df_pag = df[df["type"] == "saida"].groupby("payment_type")["amount"].sum().reset_index()

    df_pag["amount_fmt"] = df_pag["amount"].apply(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    st.dataframe(df_pag.rename(columns={
        "payment_type": "Forma de Pagamento",
        "amount_fmt": "Total (R$)"
    })[["Forma de Pagamento", "Total (R$)"]], use_container_width=True)

    st.bar_chart(df_pag.set_index("payment_type")["amount"])

    st.markdown("---")

    # ----------------------------
    # 3️⃣ GASTOS COM PAGAMENTO DE CARTÃO (MENSAL) – TOTAL GERAL
    # ----------------------------
    st.subheader("💳 Gastos com pagamento de cartão (mensal)")

    # Normaliza categoria para comparar em minúsculas
    df_temp = df.copy()
    df_temp["category_norm"] = (
        df_temp["category"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # Filtra:
    #  - saídas com forma de pagamento "Cartão de crédito"
    #  OU
    #  - saídas cuja categoria é "Pagamento de Cartão"
    df_cc = df_temp[
        (df_temp["type"] == "saida") & (
            (df_temp["payment_type"] == "Cartão de crédito") |
            (df_temp["category_norm"] == "pagamento de cartão")
        )
    ].copy()

    if df_cc.empty:
        st.info("Não há lançamentos relacionados a cartão de crédito para análise ainda.")
    else:
        # Garante tipo datetime e cria coluna de ano
        df_cc["date"] = pd.to_datetime(df_cc["date"])
        df_cc["year"] = df_cc["date"].dt.year

        # Lista de anos disponíveis (mais recente primeiro)
        anos_disponiveis = sorted(df_cc["year"].unique(), reverse=True)

        ano_atual = date.today().year
        idx_default = 0
        if ano_atual in anos_disponiveis:
            idx_default = anos_disponiveis.index(ano_atual)

        ano_ref = st.selectbox(
            "Ano de referência",
            anos_disponiveis,
            index=idx_default,
        )

        # Filtra apenas o ano escolhido
        df_cc_ano = df_cc[df_cc["year"] == ano_ref].copy()

        if df_cc_ano.empty:
            st.info(f"Não há gastos com cartão de crédito em {ano_ref}.")
        else:
            # mês numérico
            df_cc_ano["mes"] = df_cc_ano["date"].dt.month

            # 🔹 AGRUPA APENAS POR MÊS (TOTAL GERAL DO CARTÃO)
            df_cc_mes = (
                df_cc_ano.groupby("mes")["amount"]
                .sum()
                .reset_index()
            )

            # rótulo do mês (MM/AAAA)
            df_cc_mes["mes_label"] = df_cc_mes["mes"].apply(
                lambda m: f"{m:02d}/{ano_ref}"
            )

            # ---------- GRÁFICO ----------
            chart_cc = (
                alt.Chart(df_cc_mes)
                .mark_bar()
                .encode(
                    x=alt.X("mes_label:N", title="Mês"),
                    y=alt.Y("amount:Q", title="Total relacionado a cartão (R$)"),
                    tooltip=[
                        alt.Tooltip("mes_label:N", title="Mês"),
                        alt.Tooltip("amount:Q", title="Total", format=",.2f"),
                    ],
                )
                .properties(
                    width="container",
                    height=320,
                )
            )

            st.altair_chart(chart_cc, use_container_width=True)

            # ---------- TABELA RESUMO ----------
            tabela_cc = df_cc_mes[["mes_label", "amount"]].copy()
            tabela_cc["Total (R$)"] = tabela_cc["amount"].apply(
                lambda v: f"R$ {v:,.2f}"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

            tabela_cc = tabela_cc.rename(columns={"mes_label": "Mês"})
            tabela_cc = tabela_cc[["Mês", "Total (R$)"]]

            st.dataframe(tabela_cc, use_container_width=True)


    st.markdown("---")

    # ----------------------------
    # 4️⃣ EVOLUÇÃO DO PATRIMÔNIO INVESTIDO – ANO A ANO
    # ----------------------------
    st.subheader("📈 Evolução do patrimônio investido (ano a ano)")

    # Filtra somente os lançamentos de investimento
    df_inv = df[df["type"] == "investimento"].copy()

    if df_inv.empty:
        st.info("Ainda não há lançamentos de investimento para montar a evolução.")
    else:
        # Ano de cada investimento
        df_inv["year"] = pd.to_datetime(df_inv["date"]).dt.year

        # Total investido em cada ano
        df_inv_year = (
            df_inv.groupby("year")["amount"]
            .sum()
            .reset_index(name="investido_no_ano")
            .sort_values("year")
        )

        # Acumulado ao longo dos anos
        df_inv_year["investido_acumulado"] = df_inv_year["investido_no_ano"].cumsum()

        # ----- TABELA FORMATADA -----
        df_inv_view = df_inv_year.copy()
        df_inv_view["Ano"] = df_inv_view["year"].astype(int)
        df_inv_view["Investido no ano (R$)"] = df_inv_view["investido_no_ano"].apply(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        df_inv_view["Acumulado investido (R$)"] = df_inv_view["investido_acumulado"].apply(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        df_inv_view = df_inv_view[["Ano", "Investido no ano (R$)", "Acumulado investido (R$)"]]

        st.dataframe(df_inv_view, use_container_width=True)

        # ----- GRÁFICO ANO A ANO -----
        # Barras: quanto foi investido em cada ano
        # Linha: acumulado até aquele ano
        base = alt.Chart(df_inv_year).encode(
            x=alt.X("year:O", title="Ano")
        )

        barras = base.mark_bar().encode(
            y=alt.Y("investido_no_ano:Q", title="Investido no ano (R$)"),
            tooltip=[
                alt.Tooltip("year:O", title="Ano"),
                alt.Tooltip("investido_no_ano:Q", title="Investido no ano"),
                alt.Tooltip("investido_acumulado:Q", title="Acumulado até o ano"),
            ],
        )

        linha = base.mark_line(point=True, color="#60a5fa").encode(
            y=alt.Y("investido_acumulado:Q", title="Acumulado (R$)"),
        )

        chart_inv = alt.layer(barras, linha).resolve_scale(
            y="independent"
        ).properties(
            width="container",
            height=320
        )

        st.altair_chart(chart_inv, use_container_width=True)


if __name__ == "__main__":
    main()

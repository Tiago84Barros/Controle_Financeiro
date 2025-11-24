import streamlit as st
import sqlite3
from datetime import date
from dateutil.relativedelta import relativedelta
import pandas as pd

DB_PATH = "finance.db"

# ---------- Banco de Dados ----------

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,              -- 'entrada' ou 'saida'
            category TEXT NOT NULL,          -- Ex: 'Salário', 'Mercado'
            date TEXT NOT NULL,              -- 'YYYY-MM-DD'
            amount REAL NOT NULL,
            payment_type TEXT NOT NULL,      -- 'Conta', 'Cartão', 'Dinheiro', etc
            card_name TEXT,                  -- opcional
            installments INTEGER DEFAULT 1,
            description TEXT
        );
    """)
    conn.commit()
    conn.close()

def insert_transaction(t_type, category, d, amount, payment_type, card_name, installments, description):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions
        (type, category, date, amount, payment_type, card_name, installments, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (t_type, category, d, amount, payment_type, card_name, installments, description),
    )
    conn.commit()
    conn.close()

def load_data():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
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
            "saldo": 0.0,
            "perc_comprometido": 0.0,
        }, pd.DataFrame(), pd.DataFrame()

    first_day, last_day = get_month_range(ref_date)
    mask_month = (df["date"] >= first_day) & (df["date"] <= last_day)
    df_month = df[mask_month].copy()

    total_entrada = df_month.loc[df_month["type"] == "entrada", "amount"].sum()
    total_saida = df_month.loc[df_month["type"] == "saida", "amount"].sum()
    saldo = total_entrada - total_saida
    perc_comprometido = (total_saida / total_entrada * 100) if total_entrada > 0 else 0

    # Despesas por categoria no mês
    df_cat = (
        df_month[df_month["type"] == "saida"]
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
    )

    # Histórico últimos 6 meses
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
        "saldo": float(saldo),
        "perc_comprometido": float(round(perc_comprometido, 1)),
    }

    return resumo, df_cat, df_hist_pivot

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

    # --- SIDEBAR ---
    with st.sidebar:
        st.header("Filtros")
        today = date.today()
        ref_date = st.date_input("Mês de referência", value=today)
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
            "Água",
            "Luz",
            "Internet",
            "Transporte",
            "Combustível",
            "Saúde",
            "Farmácia",
            "Lazer",
            "Assinaturas",
            "Educação",
            "Restaurante",
            "Roupas",
            "Viagem",
            "Casa",
            "Outros"
        ]
    
        st.header("Novo lançamento")
    
        # 👉 Tipo fora do form, assim a tela reativa funciona
        t_type = st.radio("Tipo", ["entrada", "saida"], horizontal=True)
    
        with st.form("novo_lancamento", clear_on_submit=True):
            # Decide a lista de categorias com base no tipo já escolhido
            if t_type == "entrada":
                cat_choice = st.selectbox("Categoria", income_categories + ["Outra"])
            else:
                cat_choice = st.selectbox("Categoria", expense_categories + ["Outra"])
    
            # Se escolher "Outra", mostra campo para digitar manualmente
            if cat_choice == "Outra":
                category = st.text_input("Categoria personalizada")
            else:
                category = cat_choice
    
            d = st.date_input("Data", value=today, key="data_lanc")
            amount = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
    
            payment_type = st.selectbox(
                "Forma de pagamento", ["Conta", "Cartão de crédito", "Dinheiro", "Pix"]
            )
    
            card_name = ""
            installments = 1
            if payment_type == "Cartão de crédito":
                card_name = st.text_input("Nome do cartão")
                installments = st.number_input("Parcelas", min_value=1, value=1, step=1)
    
            description = st.text_area("Descrição (opcional)")
    
            submitted = st.form_submit_button("Salvar lançamento")
    
            if submitted:
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
                    st.error("Preencha pelo menos categoria e valor maior que zero.")

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
                    Mês atual: {ref_date.strftime("%b %Y")}
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
            <div class="cf-card-value">R$ {resumo['total_entrada']:.2f}</div>
            <div class="cf-card-extra">Somatório de todas as entradas no período selecionado.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col2.markdown(
        f"""
        <div class="cf-card cf-card-expense">
            <div class="cf-card-label">Despesas do mês</div>
            <div class="cf-card-value">R$ {resumo['total_saida']:.2f}</div>
            <div class="cf-card-extra">Somatório de todas as saídas no período.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    saldo_class = "cf-card-balance-positive" if resumo["saldo"] >= 0 else "cf-card-balance-negative"
    saldo_label_extra = "Sobrou dinheiro este mês. 👏" if resumo["saldo"] >= 0 else "Atenção: você gastou mais do que ganhou."

    col3.markdown(
        f"""
        <div class="cf-card {saldo_class}">
            <div class="cf-card-label">Saldo do mês</div>
            <div class="cf-card-value">R$ {resumo['saldo']:.2f}</div>
            <div class="cf-card-extra">{saldo_label_extra}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col4.markdown(
        f"""
        <div class="cf-card cf-card-ratio">
            <div class="cf-card-label">Renda comprometida</div>
            <div class="cf-card-value">{resumo['perc_comprometido']:.1f}%</div>
            <div class="cf-card-extra">Percentual da renda usada para despesas no mês.</div>
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
            df_cat_chart = df_cat.set_index("category")
            st.bar_chart(df_cat_chart)
            st.dataframe(
                df_cat.rename(columns={"category": "Categoria", "amount": "Valor (R$)"}),
                use_container_width=True,
            )
        else:
            st.info("Não há despesas cadastradas neste mês.")

    with col_g2:
        st.markdown("#### Histórico de 6 meses (Receitas x Despesas)")
        if not df_hist.empty:
            df_hist_chart = df_hist.copy()
            df_hist_chart.index = df_hist_chart.index.strftime("%m/%y")
            st.line_chart(df_hist_chart)
            st.dataframe(df_hist_chart, use_container_width=True)
        else:
            st.info("Ainda não há dados suficientes para histórico.")

    st.markdown("---")

    # ---------- ÚLTIMOS LANÇAMENTOS ----------
    st.markdown("### Últimos lançamentos")
    if not df.empty:
        df_sorted = df.sort_values("date", ascending=False).head(20)
        df_sorted_display = df_sorted.copy()
        df_sorted_display["date"] = df_sorted_display["date"].apply(lambda d: d.strftime("%d/%m/%Y"))
        df_sorted_display = df_sorted_display.rename(
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
        st.dataframe(df_sorted_display, use_container_width=True)
    else:
        st.info("Nenhum lançamento cadastrado ainda.")

if __name__ == "__main__":
    main()

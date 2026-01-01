import streamlit as st
import psycopg2
from datetime import date
import altair as alt
from dateutil.relativedelta import relativedelta
import pandas as pd
import hashlib

from Consulta_Tabelas import pagina_consulta_tabelas
from cartao import pagina_cartao


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

def insert_transaction(user_id, t_type, category, d, amount, payment_type, card_name, installments, description):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions
        (user_id, type, category, date, amount, payment_type, card_name, installments, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (user_id, t_type, category, d, amount, payment_type, card_name, installments, description),
    )
    conn.commit()
    conn.close()



def load_data(user_id):
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT * 
        FROM transactions 
        WHERE user_id = %s AND user_id IS NOT NULL
        ORDER BY date DESC
        """,
        conn,
        params=(str(user_id),),
    )
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ---------- Autenticação / Login ----------

def hash_password(password: str) -> str:
    """Gera um hash simples (SHA256) para a senha."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Confere se a senha digitada gera o mesmo hash salvo no banco."""
    return hash_password(password) == hashed


def authenticate_user(email: str, password: str):
    """
    Busca o usuário na tabela app_users e verifica a senha.
    Retorna um dict com dados do usuário ou None se falhar.
    """
    if not email or not password:
        return None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, email, password
        FROM app_users
        WHERE email = %s
        """,
        (email.strip().lower(),),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    user_id, user_email, stored_hash = row

    if not verify_password(password, stored_hash):
        return None

    return {"id": user_id, "email": user_email}

def create_user(email: str, password: str):
    """Cria um novo usuário no Supabase via tela de cadastro."""
    hashed = hash_password(password)

    conn = get_connection()
    cur = conn.cursor()

    # Verifica se email já existe
    cur.execute("SELECT id FROM app_users WHERE email = %s", (email.strip().lower(),))
    existing = cur.fetchone()

    if existing:
        conn.close()
        return None  # já existe

    cur.execute(
        """
        INSERT INTO app_users (email, password)
        VALUES (%s, %s)
        RETURNING id
        """,
        (email.strip().lower(), hashed),
    )

    user_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    return user_id

def login_screen():
    """Tela de login com opção de criar novo usuário."""
    
    # Mostrar título apenas quando o usuário NÃO estiver logado
    if "user" not in st.session_state or not st.session_state["user"]:
        st.title("🔐 Acesso ao seu Controle Financeiro")

    # Se já está logado:
    if "user" in st.session_state and st.session_state["user"]:
        user = st.session_state["user"]
        with st.sidebar:
            st.markdown(f"**Usuário:** {user['email']}")
            if st.button("Sair"):
                st.session_state["user"] = None
                st.rerun()
        return user

    # -----------------------
    # ABA DE LOGIN / CADASTRO
    # -----------------------
    tab_login, tab_signup = st.tabs(["Entrar", "Criar Conta"])

    # -------------------------------------
    # LOGIN
    # -------------------------------------
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submit = st.form_submit_button("Entrar")

        if submit:
            user = authenticate_user(email, password)
            if user:
                st.session_state["user"] = user
                st.session_state["user_id"] = user["id"]
                st.session_state["email"] = user["email"]
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("E-mail ou senha inválidos.")


    # -------------------------------------
    # CADASTRO
    # -------------------------------------
    with tab_signup:
        st.markdown("### Criar nova conta")

        with st.form("signup_form"):
            new_email = st.text_input("Novo e-mail")
            new_pass = st.text_input("Crie uma senha", type="password")
            confirm_pass = st.text_input("Repita a senha", type="password")

            create_btn = st.form_submit_button("Criar Conta")

        if create_btn:
            if new_pass != confirm_pass:
                st.error("As senhas não coincidem.")
            elif len(new_pass) < 4:
                st.warning("A senha deve ter pelo menos 4 caracteres.")
            else:
                user_id = create_user(new_email, new_pass)
                if user_id is None:
                    st.error("Este e-mail já está cadastrado.")
                else:
                    st.success("Conta criada com sucesso! Agora faça login.")
                    st.balloons()

    return None


    # Se NÃO estiver logado, mostra formulário central
    st.title("🔐 Login - Controle Financeiro")

    with st.form("login_form"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submit = st.form_submit_button("Entrar")

    if submit:
        user = authenticate_user(email, password)
        if user:
            st.session_state["user"] = user
            st.session_state["user_id"] = user["id"]
            st.session_state["email"] = user["email"]
            st.success("Login realizado com sucesso!")
            st.rerun()
        else:
            st.error("E-mail ou senha inválidos.")


    # Sem usuário autenticado
    return None


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

    # ✅ Fluxo de caixa considera APENAS o que mexe na conta
    #    - entradas: todas
    #    - saídas: exceto cartão de crédito (gasto futuro)
    #    - investimentos: todos (saem da conta)
    total_entrada = df_month.loc[df_month["type"] == "entrada", "amount"].sum()

    # saídas que realmente saem da conta (não cartão)
    mask_saidas_caixa = (df_month["type"] == "saida") & (
        df_month["payment_type"] != "Cartão de crédito"
    )
    total_saida = df_month.loc[mask_saidas_caixa, "amount"].sum()

    total_investimento = df_month.loc[df_month["type"] == "investimento", "amount"].sum()

    # 🔹 saldo líquido: entradas - saídas (que afetam caixa) - investimentos
    saldo = total_entrada - total_saida - total_investimento

    # 🔹 renda comprometida: saídas (que afetam caixa) + investimentos
    comprometido = total_saida + total_investimento
    perc_comprometido = (comprometido / total_entrada * 100) if total_entrada > 0 else 0

    # Despesas por categoria no mês (somente saída de fluxo)
    df_cat = (
        df_month[mask_saidas_caixa]
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
        mask_cc_hist = (df_hist["type"] == "saida") & (df_hist["payment_type"] == "Cartão de crédito")
        df_hist = df_hist[~mask_cc_hist]
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
        * {
            max-width: 100%;
            box-sizing: border-box;
        }

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
            flex-wrap: wrap;
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
            width: 100%;
            min-width: 0;
            border-radius: 0.9rem;
            padding: 0.9rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.25);
            background: radial-gradient(
                circle at top left,
                rgba(148, 163, 184, 0.15),
                rgba(15, 23, 42, 0.9)
            );
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
    # você já chamou st.set_page_config lá em cima do arquivo;
    # aqui pode até remover para evitar aviso de "set_page_config só 1 vez"
    st.set_page_config(
        page_title="Dashboard Financeiro",
        page_icon="💰",
        layout="wide",
    )

    apply_custom_style()
    init_db()

    # 1) Se não estiver logado, chama tela de login/cadastro
    user = login_screen()  # desenha login + criar conta

    if not user:
        # Ainda não logou (primeiro acesso / preenchendo formulário)
        st.stop()

    # 2) Se chegou aqui, já está logado
    user_id = user["id"]
    user_email = user["email"]

    # --- Navegação entre páginas ---
    pagina = st.sidebar.radio(
        "Navegação",
        ["Dashboard", "Análises", "Tabelas", "Cartão de Crédito"],
        horizontal=False
    )

    user_id = st.session_state["user_id"]

    # Carrega dados uma única vez (para Dashboard e Análises)
    df = load_data(user_id)

    # 👉 Se for análises, chama render_analises e sai
    if pagina == "Análises":
        render_analises(df)
        return

    # 👉 Se for consulta de tabelas, chama o módulo e não renderiza o dashboard
    if pagina == "Tabelas":
        pagina_consulta_tabelas(get_connection)
        return
    # 👉 Se for cartão de crédito, chama o módulo e não renderiza o dashboard
    if pagina == "Cartão de Crédito":
        pagina_cartao(df)
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
       # st.markdown("---")
    
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
            "Compras",
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
    
        # --- NOVO LANÇAMENTO ---
        st.markdown("<hr style='margin: 0.75rem 0;'>", unsafe_allow_html=True)
        st.subheader("Novo lançamento")
        
        # -------------------------------------------
        # 1) Tipo (reativo)
        # -------------------------------------------
        t_type = st.radio(
            "Tipo",
            ["entrada", "saida", "investimento"],
            horizontal=True,
        )
        
        # Divisor
        st.markdown("<hr style='margin-top:0; margin-bottom:12px; opacity:0.35;'>", unsafe_allow_html=True)
        
        # -------------------------------------------
        # 2) Forma de pagamento (só para SAÍDA)
        # -------------------------------------------
        if t_type == "saida":
            payment_type = st.selectbox(
                "Forma de pagamento",
                ["Conta", "Cartão de crédito", "Dinheiro", "Pix"],
            )
        else:
            payment_type = "Conta"
        
        # Deve mostrar campos de cartão?
        show_card_fields = (t_type == "saida" and payment_type == "Cartão de crédito")
        
        # Outro divisor
        st.markdown("<hr style='margin-top:0; margin-bottom:12px; opacity:0.35;'>", unsafe_allow_html=True)
        
        # -------------------------------------------
        # 3) FORMULÁRIO (limpa depois de salvar)
        # -------------------------------------------
        with st.form("novo_lancamento", clear_on_submit=True):
        
            # Categorias dinâmicas
            if t_type == "entrada":
                cat_choice = st.selectbox("Categoria", income_categories + ["Outra"])
            elif t_type == "saida":
                cat_choice = st.selectbox("Categoria", expense_categories + ["Outra"])
            else:
                cat_choice = st.selectbox("Categoria", investment_categories)
        
            if cat_choice == "Outra":
                category = st.text_input("Categoria personalizada")
            else:
                category = cat_choice
        
            # Data
            d = st.date_input("Data", value=today, format="DD/MM/YYYY")
        
            # Valor (sempre aparece)
            valor_str = st.text_input("Valor (R$)", value="", placeholder="0,00")
        
            # -------------------------------------------
            # Campos de cartão — SÓ aparecem se for saída + cartão
            # -------------------------------------------
            if show_card_fields:
                col_parc, col_card = st.columns([1, 2])
        
                with col_parc:
                    installments = st.number_input(
                        "Parcelas",
                        min_value=1,
                        value=1,
                        step=1,
                    )
        
                with col_card:
                    card_name = st.text_input("Cartão")
            else:
                installments = 1
                card_name = ""
        
            # Descrição
            description = st.text_area("Descrição (opcional)")
        
            # Botão do form
            submitted = st.form_submit_button("Salvar lançamento", use_container_width=True)
        
        # -------------------------------------------
        # PROCESSAMENTO DO ENVIO
        # -------------------------------------------
        if submitted:
            amount = parse_brl_to_float(valor_str)
        
            if amount > 0 and category.strip():
                insert_transaction(
                    user_id,
                    t_type,
                    category,
                    d,
                    amount,
                    payment_type,
                    card_name,
                    installments,
                    description,
                )
                st.success("Lançamento salvo com sucesso!")
                st.rerun()
            else:
                st.error("Preencha categoria e valor maior que zero.")

    if "user_id" not in st.session_state:
        st.error("Erro: usuário não autenticado. Volte para a tela de login.")
        st.stop()

    user_id = st.session_state["user_id"]

    # --- DADOS ---
    df = load_data(user_id)
       
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
            # df_hist é um pivot com index = ym (primeiro dia do mês) e colunas = tipos
            df_hist_chart = df_hist.copy()
    
            # ✅ garante que o índice é datetime e ordena cronologicamente
            df_hist_chart.index = pd.to_datetime(df_hist_chart.index)
            df_hist_chart = df_hist_chart.sort_index()
    
            # ✅ renomeia coluna de investimento para nome amigável (se existir)
            if "investimento" in df_hist_chart.columns:
                df_hist_chart = df_hist_chart.rename(columns={"investimento": "Investimentos"})
    
            # ✅ converte para formato longo para o Altair
            df_hist_chart = df_hist_chart.reset_index()
            # após reset_index, a coluna pode virar "index" dependendo do pandas
            if "index" in df_hist_chart.columns and "ym" not in df_hist_chart.columns:
                df_hist_chart = df_hist_chart.rename(columns={"index": "ym"})
            elif "ym" not in df_hist_chart.columns:
                # fallback defensivo (não costuma ser necessário)
                df_hist_chart = df_hist_chart.rename(columns={df_hist_chart.columns[0]: "ym"})
    
            df_long = df_hist_chart.melt(
                id_vars="ym",
                var_name="Tipo",
                value_name="Valor"
            )
    
            # ✅ garante que o eixo X é temporal
            df_long["ym"] = pd.to_datetime(df_long["ym"])
    
            chart_hist = (
                alt.Chart(df_long)
                .mark_line(point=True)
                .encode(
                    x=alt.X("ym:T", title="Mês", axis=alt.Axis(format="%m/%y")),
                    y=alt.Y("Valor:Q", title="Valor (R$)"),
                    color=alt.Color("Tipo:N", title="Tipo"),
                    tooltip=[
                        alt.Tooltip("ym:T", title="Mês", format="%m/%y"),
                        alt.Tooltip("Tipo:N", title="Tipo"),
                        alt.Tooltip("Valor:Q", title="Valor", format=",.2f"),
                    ],
                )
                .properties(
                    width="container",
                    height=320
                )
            )
    
            st.altair_chart(chart_hist, use_container_width=True)
    
            # ✅ tabela formatada (mantém a visualização como você já fazia)
            df_hist_tab = df_hist.copy()
            df_hist_tab.index = pd.to_datetime(df_hist_tab.index)
            df_hist_tab = df_hist_tab.sort_index()
    
            df_hist_fmt = df_hist_tab.copy()
            for col in df_hist_fmt.columns:
                df_hist_fmt[col] = df_hist_fmt[col].apply(
                    lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
    
            df_hist_fmt = df_hist_fmt.rename_axis("Mês").reset_index()
            # formata mês na tabela como MM/AA
            df_hist_fmt["Mês"] = pd.to_datetime(df_hist_fmt["Mês"]).dt.strftime("%m/%y")
    
            st.dataframe(df_hist_fmt, use_container_width=True)
    
        else:
            st.info("Ainda não há dados suficientes para histórico.")


            
        st.markdown("---")

    # ---------- ÚLTIMOS LANÇAMENTOS ----------
    st.markdown("### Últimos lançamentos")

    if not df.empty:

        # 🔹 função auxiliar para pegar últimos N de um tipo
        def get_last_n(df_base, tipo, n=10):
            df_tipo = df_base[df_base["type"] == tipo].copy()
            if df_tipo.empty:
                return df_tipo
            # ordena por data (mais recente primeiro) e pega N
            return df_tipo.sort_values(by="date", ascending=False).head(n)

        # 🔹 últimos 10 de cada tipo
        df_ult_entrada = get_last_n(df, "entrada", 20)
        df_ult_saida = get_last_n(df, "saida", 20)
        df_ult_invest = get_last_n(df, "investimento", 20)

        # 🔹 concatena mantendo ordem: entrada → investimento → saída
        df_sorted = pd.concat(
            [df_ult_entrada, df_ult_invest, df_ult_saida],
            ignore_index=True
        )

        if df_sorted.empty:
            st.info("Ainda não há lançamentos suficientes para exibir nesta seção.")
            return


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

            # 🔹 Formata o valor como texto BRL para edição (permite vírgula e ponto)
            df_edit["Valor"] = df_edit["Valor"].apply(
                lambda v: f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )

            edited_df = st.data_editor(
                df_edit,
                num_rows="fixed",
                hide_index=True,
                key="editor_ultimos",
                column_config={
                    "ID": st.column_config.NumberColumn("ID", disabled=True),
                    "Data": st.column_config.DateColumn("Data"),
                    # 🔹 Agora é TextColumn para aceitar vírgula/ponto
                    "Valor": st.column_config.TextColumn(
                        "Valor (R$)",
                        help="Use vírgula como separador decimal (ex: 1.234,56)."
                    ),
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

                # 🔹 Converte string BRL para float usando sua função
                to_update["amount"] = to_update["amount"].apply(parse_brl_to_float).astype(float)
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
            xOffset="type",                                # 👉 BARRAS LADO A LADO
            color=alt.Color(
                "type:N",
                title="Tipo",
                scale=alt.Scale(
                    domain=["entrada", "saida", "investimento"],
                    range=["#3b82f6", "#ef4444", "#22c55e"],  # azul, vermelho, verde
                ),
            ),
            tooltip=["year:N", "type:N", "amount:Q"],
        )
        .properties(
            width="container",
            height=320
        )
    )
    
    st.altair_chart(chart_yoy, use_container_width=True)

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
            (df_temp["payment_type"] == "Conta") &
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
                    x=alt.X("mes_label:N", title="Mês",
                           sort=["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]),
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

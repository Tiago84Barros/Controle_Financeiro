
# Dashboard Financeiro - Streamlit

Aplicativo simples de controle financeiro rodando em Streamlit + SQLite.

## Como rodar localmente

1. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

2. Rode o app:

   ```bash
   streamlit run streamlit_app.py
   ```

3. Acesse o endereço mostrado no terminal (geralmente http://localhost:8501).

## Deploy no Streamlit Community Cloud

1. Suba estes arquivos para um repositório no GitHub.
2. No Streamlit Community Cloud, crie um novo app apontando para esse repositório.
3. Defina `streamlit_app.py` como arquivo principal.
4. O banco `finance.db` será criado automaticamente no servidor.

from Controle import create_user

email = "meuemail@teste.com"
password = "minha_senha_secreta"

uid = create_user(email, password)
print("Usuário criado com ID:", uid)

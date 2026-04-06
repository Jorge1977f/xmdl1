# Backend de licença do XMDL

Para teste local simples, sem ambiente virtual:

1. Abra `backend/.env`
2. Preencha somente `LICENSE_PG_PASSWORD`
3. Rode `1_INSTALAR_DEPENDENCIAS_SEM_VENV.bat`
4. Rode `2_INICIAR_BACKEND_LOCAL.bat`
5. Abra `http://127.0.0.1:8080/docs`
6. Abra o app com `4_ABRIR_XMDL_TESTE.bat`

O backend monta a conexão do Supabase automaticamente usando o projeto:
`pqwrohnwheesnwueekpv`

Em produção, o cliente final não usa backend local. A API fica online em HTTPS.

## Teste rápido com Mercado Pago

1. Copie `backend/.env.example` para `backend/.env`.
2. Preencha `LICENSE_PG_PASSWORD`.
3. Em `LICENSE_MP_ACCESS_TOKEN`, cole o **Access Token** do Mercado Pago.
   - Para teste, use o token da área **Test credentials**.
   - Usuário/senha da conta de teste **não** substituem o Access Token.
4. Deixe `LICENSE_PIX_MODE=mercadopago`.
5. Se estiver testando localmente, mantenha `LICENSE_API_BASE_URL=http://127.0.0.1:8080`.
6. No desktop, copie `.env.example` para `.env` e confirme `XMLDLK_LICENSE_API_URL=http://127.0.0.1:8080`.
7. Rode o backend e abra `/health` para confirmar:
   - `database_ready: true`
   - `mode: mercadopago`
   - `mercadopago_ready: true`
8. No módulo **Licenças**, gere o Pix.
9. Se quiser testar o fluxo inteiro sem pagamento real, use o botão **Simular pagamento**.

Se `mercadopago_ready` vier `false`, normalmente faltou token ou webhook.

# Contrato esperado pelo app para licenciamento

## 1) Sincronizar instalação e trial
`POST /api/licensing/installations/sync`

### Body
```json
{
  "buyer": {
    "nome": "Empresa Exemplo",
    "documento": "12345678000199",
    "email": "financeiro@empresa.com",
    "telefone": "49999999999"
  },
  "installation": {
    "machine_id": "hash-da-maquina",
    "machine_name": "PC-FISCAL-01",
    "install_id": "uuid-local",
    "app_version": "1.0.0",
    "platform": "Windows-10"
  },
  "token": "token-opcional"
}
```

### Response esperada
```json
{
  "client_id": "uuid",
  "installation_id": "uuid",
  "token": "token-assinado-ou-jwt",
  "server_time": "2026-03-29T12:00:00Z",
  "buyer": {
    "nome": "Empresa Exemplo",
    "documento": "12345678000199",
    "email": "financeiro@empresa.com",
    "telefone": "49999999999"
  },
  "trial": {
    "started_at": "2026-03-29T12:00:00Z",
    "expires_at": "2026-04-05T12:00:00Z"
  },
  "license": {
    "status": "TRIAL",
    "message": "Você tem 7 dias para testar.",
    "downloads_allowed": true,
    "licenses_total": 0,
    "licenses_in_use": 0
  },
  "payment": {
    "order_id": "",
    "pix_copy_paste": "",
    "pix_qr_code_base64": "",
    "expires_at": null
  }
}
```

## 2) Gerar pedido Pix
`POST /api/licensing/orders`

### Body
```json
{
  "buyer": {
    "nome": "Empresa Exemplo",
    "documento": "12345678000199",
    "email": "financeiro@empresa.com",
    "telefone": "49999999999"
  },
  "installation": {
    "machine_id": "hash-da-maquina",
    "machine_name": "PC-FISCAL-01",
    "install_id": "uuid-local"
  },
  "order": {
    "quantity": 6,
    "expected_total": 294.41
  }
}
```

### Regra de preço
- 1 a 5 licenças: R$ 49,90 cada
- da 6ª em diante: 10% de desconto por licença adicional

### Response esperada
```json
{
  "payment": {
    "order_id": "uuid-do-pedido",
    "pix_copy_paste": "000201...",
    "pix_qr_code_base64": "<base64_png>",
    "expires_at": "2026-03-29T13:00:00Z",
    "message": "Pedido Pix gerado. Você tem 1 hora para pagar."
  }
}
```

## 3) Regras de negócio sugeridas no backend
- o trial usa a data/hora do servidor, nunca a do PC do usuário
- o cliente é identificado pelo documento (CPF/CNPJ)
- a instalação é identificada pelo `machine_id`
- se o cliente já teve trial antes, um novo PC não reinicia o período grátis
- após expirar o trial, `downloads_allowed` deve voltar `false`
- XMLs já baixados continuam locais; o backend precisa bloquear só novas capturas
- quando um pedido Pix for pago, aumente `licenses_total` do cliente
- ative a instalação atual se houver vaga livre
- a partir da 6ª licença, aplique 10% de desconto nas licenças adicionais

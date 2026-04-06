Ajustes desta versão:
- Tela "Visualizar XMLs" sem repetir a empresa da barra superior.
- Filtros reorganizados para deixar período e opções mais visíveis.
- Duplo clique abre exatamente a linha clicada, evitando abrir outro XML/PDF por seleção anterior.
- PDF DANFSe ajustado para ficar mais próximo do modelo oficial:
  - chave exibida sem prefixo NFS/NFSE;
  - bloco do QR com texto menor;
  - bloco de intermediário em duas linhas.

Validação feita:
- py_compile em app/ui/xmls_page.py e app/services/xml_pdf_service.py
- geração de PDF de teste a partir de XML real extraído do retorno da API

Ajustes desta versão

1. Visualizar XML/PDF
- Corrigida a lógica que confundia PDFs por número parcial.
- Agora a procura do PDF usa o XML da própria nota e tokens exatos (chave/stem), evitando abrir o PDF de outra NFSe.
- O botão Visualizar XML/PDF passou a abrir a linha atual da grade por padrão.

2. Geração de PDF
- Geração ficou mais tolerante a XMLs de tomada: se a extração de campos extras falhar, o sistema ainda tenta gerar o PDF.
- Melhorada a escolha do bloco correto de tomador/prestador, priorizando blocos mais completos com endereço/cidade/CEP.
- Melhorada a captura do município do tomador.

3. Relatórios
- Ao trocar a empresa no seletor global, a página de relatórios agora atualiza automaticamente.
- A página também tenta carregar automaticamente a empresa já selecionada ao abrir.
- Melhorada a identificação de prestada/tomada usando CNPJ e também o nome da empresa quando o XML vier incompleto.

Arquivos principais alterados
- app/utils/document_viewer.py
- app/ui/xmls_page.py
- app/services/xml_pdf_service.py
- app/ui/relatorios_page.py

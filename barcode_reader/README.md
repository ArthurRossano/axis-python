# Sistema de Leitura de Códigos de Barras com Câmera Axis

Este sistema permite capturar imagens de uma câmera Axis e decodificar códigos QR e códigos de barras presentes nas imagens.

## Requisitos

- Python 3.7 ou superior
- Câmera Axis com acesso via API VAPIX
- Bibliotecas Python listadas em `requirements.txt`

## Instalação

1. Clone ou baixe este repositório
2. Instale as dependências:

```
pip install -r requirements.txt
```

### Dependências no Windows

No Windows, a biblioteca `pyzbar` pode exigir a instalação do ZBar. Você pode baixar o instalador em:
https://github.com/NaturalHistoryMuseum/ZBarWin64

## Uso

1. Execute o script principal:

```
python axis_barcode_reader.py
```

2. Configure os parâmetros da câmera:
   - IP da câmera
   - Nome de usuário
   - Senha

3. Clique em "Testar Conexão" para verificar se a câmera está acessível

4. Clique em "Iniciar Leitura" para começar a capturar e decodificar códigos

## Funcionalidades

- Leitura de códigos QR e códigos de barras
- Interface gráfica simples
- Exibição dos dados decodificados
- Teste de conexão com a câmera

## Solução de Problemas

Se encontrar problemas com a leitura de códigos:

1. Verifique se a câmera está corretamente configurada e acessível
2. Certifique-se de que o código está bem iluminado e visível
3. Ajuste a posição da câmera para melhor visualização do código
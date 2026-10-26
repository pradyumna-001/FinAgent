# Empresas de Crédito

## Cabo frio:
    - aprova credito
    - financiatta
    - gm cred
    - cred money
    - ng cred
    - unacred
    - commerx class

## Araruama:
    - cred facil
    - arecred soluções financeiras
    - socinal financeira

| # | Problema | Solução |
|---|----------|---------|
| 1 | Cada banco tem sistema/API próprio; atendente digita os mesmos dados manualmente em cada portal e não tem visão unificada de status | **Hub de integração multi-banco**: camada central que recebe os dados uma vez, submete a proposta via API pra cada banco conveniado e consolida status/aprovação/taxa num painel único |
| 2 | Não dá pra saber se o cliente tem margem consignável antes de tentar vender — tempo gasto em lead que nunca vai fechar | **Consulta automática de margem/elegibilidade**: integração com as bases (INSS, eSocial, folha) pra pré-qualificar o lead antes de acionar o vendedor |
| 3 | Cliente abandona sozinho a etapa de autenticação (Gov.br/biometria) e o correspondente perde a venda sem saber que travou | **Monitor de funil com alerta automático**: detecta proposta parada numa etapa e dispara lembrete (cliente e/ou atendente) pra retomar antes de perder o negócio |
| 4 | Comissão de cada banco tem prazo/regra diferente; reconciliação é manual e sujeita a erro, gerando perda de receita invisível | **Reconciliação automática de comissões**: cruza o esperado (por regra de cada convênio) com o que efetivamente caiu, e sinaliza divergência |
| 5 | Falta trilha auditável por operação, exigida pelas novas normas de autorregulação/MCB — hoje é e-mail e papel | **Log estruturado de compliance**: registro automático de cada etapa da proposta, pronto pra auditoria e pra negociar com os bancos como diferencial |
| 6 | Time comercial perde tempo qualificando lead frio e conferindo documento incompleto/ilegível antes de avançar | **Triagem automatizada de lead e documento**: primeiro filtro (via WhatsApp e OCR) que só passa pro humano o que já está qualificado e completo |

O problema 1 é a base de tudo — os problemas 2, 4 e 5 praticamente dependem de já existir esse hub central de dados pra funcionar bem, então ele também é a melhor porta de entrada comercial: resolve a dor mais visível primeiro e abre caminho pra vender os outros como evolução do mesmo sistema.
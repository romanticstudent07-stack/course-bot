# packages/shared/

Общие типы и OpenAPI-контракт `/miniapp/v1`.

## OpenAPI-контракт `/miniapp/v1`

**Каноничный источник:**
`docs/architecture/build/miniapp-api-contract.yaml`
(зеркало DOCS-course-bot, обновляется автоматически через sync-workflow).

**Не копировать содержимое сюда** — риск разъезда двух источников.
При генерации типов (`openapi-typescript`, `datamodel-codegen`) — читать
только из зеркала:

```bash
# Пример: генерация TypeScript-типов
npx openapi-typescript \
    ../../docs/architecture/build/miniapp-api-contract.yaml \
    -o types/miniapp-api.ts

# Пример: генерация Python pydantic-моделей
datamodel-codegen \
    --input ../../docs/architecture/build/miniapp-api-contract.yaml \
    --output ../shared_py/miniapp_api.py \
    --output-model-type pydantic_v2.BaseModel

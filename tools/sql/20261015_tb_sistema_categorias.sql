-- LuftBase 0.1.0a109 - tb_sistema: novas categorias (API, FERRAMENTA, RELATORIO, INTEGRACAO).
--
-- Equivale a migracao Alembic 20261015_0017. Rode DEPOIS de 20261015_tb_sistema_tipo_de_integracao.sql
-- (o carimbo da revisao so avanca nessa ordem). Aditivo: so alarga o CHECK; nenhuma linha muda.
-- Repetivel e transacional. Carimba a revisao 20261015_0017 so se o core estiver na 20261015_0016.

BEGIN;

ALTER TABLE core.tb_sistema DROP CONSTRAINT IF EXISTS ck_core_sistema_categoria;
ALTER TABLE core.tb_sistema ADD CONSTRAINT ck_core_sistema_categoria
    CHECK (categoria IN ('APLICACAO', 'API', 'SERVICO', 'FERRAMENTA', 'RELATORIO', 'INTEGRACAO', 'HUB'));

UPDATE core.alembic_version SET version_num = '20261015_0017' WHERE version_num = '20261015_0016';

COMMIT;

-- Conferencia
SELECT version_num AS revisao_do_core FROM core.alembic_version;
SELECT pg_get_constraintdef(oid) FROM pg_constraint
WHERE conname = 'ck_core_sistema_categoria' AND conrelid = 'core.tb_sistema'::regclass;

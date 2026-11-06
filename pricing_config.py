"""Ativação explícita durante a homologação, independente do preço de cada item."""
import os


def enabled():
    return os.environ.get('KSB_DYNAMIC_PRICING') == '1'


def ensure_test_database():
    if os.environ.get('KSB_ENVIRONMENT') != 'teste':
        raise RuntimeError('Migrações de precificação autorizadas somente no ambiente teste.')
    host=os.environ.get('DB_HOST','')
    expected=os.environ.get('KSB_TEST_ENDPOINT_ID','')
    if not expected.startswith('ep-') or host not in (expected+'.'+os.environ.get('KSB_TEST_ENDPOINT_DOMAIN',''), expected+'-pooler.'+os.environ.get('KSB_TEST_ENDPOINT_DOMAIN','')):
        raise RuntimeError('O banco configurado não é o endpoint isolado de homologação.')

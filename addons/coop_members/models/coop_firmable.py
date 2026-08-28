import hashlib

from odoo import models


class CoopFirmable(models.AbstractModel):
    """Contrato común de la firma con hash de contenido.

    Antes de este mixin el mecanismo estaba copiado en `coop.certificado`,
    `coop.asignacion.herramienta` y `coop.assembly` / `coop.acta.firma`. Cada
    copia es una oportunidad de que divergan, y la forma en que divergen es la
    peor que puede tener esta app: decir "firma válida" cuando no lo es.

    Acá vive lo único que NO puede diferir entre modelos:
      - el algoritmo del hash (`_hash_de`)
      - la regla de validez (`_firma_es_valida`)

    Cada modelo implementa `_contenido_para_hash()`: qué texto se firma es lo
    único propio de cada uno. Los campos calculados (`hash_actual`,
    `firma_valida`) y la acción de firmar siguen en cada modelo porque su forma
    todavía difiere (un firmante inline vs. filas con rol); lo que importa es
    que los tres deciden la validez con el mismo método.
    """
    _name = 'coop.firmable'
    _description = 'Mecanismo común de firma con hash de contenido'

    def _contenido_para_hash(self):
        """El texto canónico que se firma. Lo implementa cada modelo."""
        raise NotImplementedError(
            '%s tiene que implementar _contenido_para_hash()' % self._name)

    @staticmethod
    def _hash_de(contenido):
        """SHA-256 hex del contenido. Un solo lugar define el algoritmo."""
        return hashlib.sha256((contenido or '').encode('utf-8')).hexdigest()

    def _hash_actual(self):
        """Hash del contenido tal como está ahora (y el que se registra al
        momento de firmar)."""
        self.ensure_one()
        return self._hash_de(self._contenido_para_hash())

    def _firma_es_valida(self, hash_firmado):
        """Regla única de validez: hay un hash firmado y coincide con el
        contenido actual. Si esto se rompe, se rompe en los tres modelos."""
        self.ensure_one()
        return bool(hash_firmado) and hash_firmado == self._hash_actual()

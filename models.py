from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.orm import relationship

from database import Base


# =============================
# USUARIOS
# =============================
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    nombre = Column(String(150), nullable=False)
    es_admin = Column(Boolean, default=False)
    password_hash = Column(String(255), nullable=False)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


# =============================
# CLIENTES
# =============================
class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String)
    email = Column(String)
    direccion = Column(String)
    ciudad = Column(String)
    notas = Column(String)
    creado_en = Column(DateTime, default=datetime.utcnow)

    movimientos = relationship("MovimientoCtaCte", back_populates="cliente")
    pedidos = relationship("Pedido", back_populates="cliente")
    @property
    def saldo(self) -> float:
        """Saldo calculado en base a los movimientos de cuenta corriente."""
        saldo = 0.0
        for m in self.movimientos or []:
            # Importante: TipoMovimiento se define más abajo en este mismo archivo
            if m.tipo == TipoMovimiento.debito:
                saldo += m.monto
            else:
                saldo -= m.monto
        return saldo


# =============================
# PRODUCTOS
# =============================
class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    precio_compra = Column(Float, nullable=False)
    precio_venta = Column(Float, nullable=False)
    descripcion = Column(String)
    contenido = Column(String)
    activo = Column(Boolean, default=True)
    creado_en = Column(DateTime, default=datetime.utcnow)

    items = relationship("PedidoItem", back_populates="producto")


# =============================
# CUENTA CORRIENTE
# =============================
class TipoMovimiento(PyEnum):
    debito = "debito"
    credito = "credito"


class MovimientoCtaCte(Base):
    __tablename__ = "movimientos_cta_cte"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"))
    tipo = Column(Enum(TipoMovimiento), nullable=False)
    monto = Column(Float, nullable=False)
    descripcion = Column(String, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)

    cliente = relationship("Cliente", back_populates="movimientos")


# =============================
# PEDIDOS
# =============================
class EstadoPedido(PyEnum):
    pendiente = "pendiente"
    entregado = "entregado"


class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)

    fecha_pedido = Column(DateTime, default=datetime.utcnow)
    fecha_entrega = Column(DateTime)

    medio_contacto = Column(String)
    observaciones = Column(String)

    descuento = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    estado = Column(Enum(EstadoPedido), default=EstadoPedido.pendiente)

    cliente = relationship("Cliente", back_populates="pedidos")
    items = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan")

    @property
    def ganancia_total(self) -> float:
        return sum(item.ganancia for item in self.items)


class PedidoItem(Base):
    __tablename__ = "pedido_items"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)

    descripcion_item = Column(String, nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_venta_unitario = Column(Float, nullable=False)
    costo_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    pedido = relationship("Pedido", back_populates="items")
    producto = relationship("Producto", back_populates="items")

    @property
    def ganancia(self) -> float:
        return (self.precio_venta_unitario - self.costo_unitario) * self.cantidad

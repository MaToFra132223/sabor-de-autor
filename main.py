# main.py
from datetime import datetime, timedelta, date
from typing import List
import hashlib
import io
import csv

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy import func  # <-- AÑADIR ESTO
from sqlalchemy.orm import Session, relationship
from sqlalchemy.orm import joinedload  # <-- Y ESTO


from sqlalchemy import asc, desc


from starlette.middleware.sessions import SessionMiddleware

from database import Base, engine, get_db, SessionLocal
from models import (
    Producto,
    Cliente,
    MovimientoCtaCte,
    TipoMovimiento,
    Pedido,
    PedidoItem,
    EstadoPedido,
    Usuario,
)

# =========================
# CONFIGURACIÓN BÁSICA
# =========================

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sabor de Autor - Gestión")

# Static y templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = datetime.now  # helper para plantillas

# Sesiones (usuario logueado)
app.add_middleware(
    SessionMiddleware,
    secret_key="SABOR_DE_AUTOR_SECRET_2025",  # podés cambiarlo
)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def is_logged_in(request: Request) -> bool:
    """Devuelve True si hay usuario en sesión."""
    return bool(request.session.get("user"))


def ensure_admin_user():
    """Crea el usuario admin por defecto si no existe."""
    db = SessionLocal()
    try:
        admin = db.query(Usuario).filter(Usuario.username == "admin").first()
        if not admin:
            admin = Usuario(
                username="admin",
                nombre="Administrador",
                es_admin=True,
                password_hash=hash_password("sda2025"),
                activo=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


ensure_admin_user()

# =========================
# LOGIN / LOGOUT
# =========================

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    # Si ya está logueado, lo mando al inicio
    if is_logged_in(request):
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": None,
            "username": "",
        }
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(Usuario)
        .filter(Usuario.username == username, Usuario.activo == True)
        .first()
    )

    if user and user.password_hash == hash_password(password):
        request.session["user"] = {
            "id": user.id,
            "username": user.username,
            "nombre": user.nombre,
            "es_admin": user.es_admin,
        }
        return RedirectResponse("/", status_code=303)

    # Credenciales incorrectas
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": "Usuario o contraseña incorrectos",
            "username": username,
        }
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)




@app.get("/debug-db")
def debug_db(db: Session = Depends(get_db)):
    # URL real de la base que está usando la app
    url = str(db.bind.url)

    result = {}
    for model, name in [
        (Usuario, "usuarios"),
        (Producto, "productos"),
        (Pedido, "pedidos"),
    ]:
        try:
            count = db.query(model).count()
        except Exception as e:
            count = f"error: {e!r}"
        result[name] = count

    return JSONResponse(
        {
            "db_url": url,
            "tablas": result,
        }
    )



# =========================
# HOME
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "titulo": "Sabor de Autor – Gestión",
            "active_page": "home",
        }
    )


# =========================
# PRODUCTOS
# =========================
@app.get("/productos", response_class=HTMLResponse)
def listar_productos(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    productos = db.query(Producto).order_by(asc(Producto.nombre)).all()
    return templates.TemplateResponse(
        "productos/lista.html",
        {
            "request": request,
            "productos": productos,
            "active_page": "productos",
        }
    )


@app.get("/productos/nuevo", response_class=HTMLResponse)
def nuevo_producto(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "productos/form.html",
        {
            "request": request,
            "producto": None,
            "active_page": "productos",
        }
    )


@app.post("/productos/guardar")
def guardar_producto(
    nombre: str = Form(...),
    precio_compra: float = Form(...),
    precio_venta: float = Form(...),
    descripcion: str = Form(""),
    contenido: str = Form(""),
    db: Session = Depends(get_db),
):
    producto = Producto(
        nombre=nombre,
        precio_compra=precio_compra,
        precio_venta=precio_venta,
        descripcion=descripcion,
        contenido=contenido,
    )
    db.add(producto)
    db.commit()
    return RedirectResponse("/productos", status_code=303)


@app.get("/productos/editar/{producto_id}", response_class=HTMLResponse)
def editar_producto(
    producto_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    producto = db.get(Producto, producto_id)
    return templates.TemplateResponse(
        "productos/form.html",
        {
            "request": request,
            "producto": producto,
            "active_page": "productos",
        }
    )


@app.post("/productos/actualizar/{producto_id}")
def actualizar_producto(
    producto_id: int,
    nombre: str = Form(...),
    precio_compra: float = Form(...),
    precio_venta: float = Form(...),
    descripcion: str = Form(""),
    contenido: str = Form(""),
    activo: bool = Form(False),
    db: Session = Depends(get_db),
):
    producto = db.get(Producto, producto_id)

    producto.nombre = nombre
    producto.precio_compra = precio_compra
    producto.precio_venta = precio_venta
    producto.descripcion = descripcion
    producto.contenido = contenido
    producto.activo = activo

    db.commit()
    return RedirectResponse("/productos", status_code=303)


# =========================
# CLIENTES
# =========================
@app.get("/clientes", response_class=HTMLResponse)
def listar_clientes(
    request: Request,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    query = db.query(Cliente)

    if q:
        patron = f"%{q}%"
        query = query.filter(
            Cliente.nombre.ilike(patron) |
            Cliente.telefono.ilike(patron)
        )

    clientes = query.order_by(asc(Cliente.nombre)).all()

    return templates.TemplateResponse(
        "clientes/lista.html",
        {
            "request": request,
            "clientes": clientes,
            "q": q or "",
            "active_page": "clientes",
        }
    )


@app.get("/clientes/nuevo", response_class=HTMLResponse)
def nuevo_cliente(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "clientes/form.html",
        {
            "request": request,
            "cliente": None,
            "active_page": "clientes",
        }
    )


@app.post("/clientes/guardar")
def guardar_cliente(
    nombre: str = Form(...),
    telefono: str = Form(""),
    email: str = Form(""),
    direccion: str = Form(""),
    ciudad: str = Form(""),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    cliente = Cliente(
        nombre=nombre,
        telefono=telefono,
        email=email,
        direccion=direccion,
        ciudad=ciudad,
        notas=notas,
    )
    db.add(cliente)
    db.commit()
    return RedirectResponse("/clientes", status_code=303)


@app.get("/clientes/editar/{cliente_id}", response_class=HTMLResponse)
def editar_cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    cliente = db.get(Cliente, cliente_id)
    return templates.TemplateResponse(
        "clientes/form.html",
        {
            "request": request,
            "cliente": cliente,
            "active_page": "clientes",
        }
    )


@app.post("/clientes/actualizar/{cliente_id}")
def actualizar_cliente(
    cliente_id: int,
    nombre: str = Form(...),
    telefono: str = Form(""),
    email: str = Form(""),
    direccion: str = Form(""),
    ciudad: str = Form(""),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    cliente = db.get(Cliente, cliente_id)

    cliente.nombre = nombre
    cliente.telefono = telefono
    cliente.email = email
    cliente.direccion = direccion
    cliente.ciudad = ciudad
    cliente.notas = notas

    db.commit()
    return RedirectResponse("/clientes", status_code=303)


# =========================
# CUENTA CORRIENTE
# =========================
@app.get("/clientes/{cliente_id}/cta-cte", response_class=HTMLResponse)
def ver_cta_cte(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    cliente = db.get(Cliente, cliente_id)

    movimientos_db = (
        db.query(MovimientoCtaCte)
        .filter(MovimientoCtaCte.cliente_id == cliente_id)
        .order_by(asc(MovimientoCtaCte.fecha))
        .all()
    )

    mov_rows = []
    saldo = 0.0

    for m in movimientos_db:
        if m.tipo == TipoMovimiento.debito:
            saldo += m.monto
            es_debito = True
        else:
            saldo -= m.monto
            es_debito = False

        mov_rows.append(
            {
                "mov": m,
                "saldo": saldo,
                "es_debito": es_debito,
            }
        )

    return templates.TemplateResponse(
        "clientes/cta_cte.html",
        {
            "request": request,
            "cliente": cliente,
            "mov_rows": mov_rows,
            "saldo_final": saldo,
            "active_page": "clientes",
        }
    )


@app.post("/clientes/{cliente_id}/registrar-pago")
def registrar_pago(
    cliente_id: int,
    monto: float = Form(...),
    descripcion: str = Form("Pago"),
    db: Session = Depends(get_db),
):
    pago = MovimientoCtaCte(
        cliente_id=cliente_id,
        tipo=TipoMovimiento.credito,
        monto=monto,
        descripcion=descripcion,
    )
    db.add(pago)
    db.commit()
    return RedirectResponse(
        f"/clientes/{cliente_id}/cta-cte",
        status_code=303,
    )


# =========================
# PEDIDOS (LISTA / TABLERO / ALTA / EDICIÓN)
# =========================
@app.get("/pedidos", response_class=HTMLResponse)
def listar_pedidos(
    request: Request,
    buscar: str = "",
    estado: str = "todos",
    desde: str = "",
    hasta: str = "",
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    query = (
        db.query(Pedido)
        .options(joinedload(Pedido.cliente))
    )

    # 🔍 Filtro por cliente (texto)
    if buscar:
        patron = f"%{buscar.strip()}%"
        query = query.filter(
            Pedido.cliente.has(Cliente.nombre.ilike(patron))
        )

    # ✅ Filtro por estado
    if estado == "pendiente":
        query = query.filter(Pedido.estado == EstadoPedido.pendiente)
    elif estado == "entregado":
        query = query.filter(Pedido.estado == EstadoPedido.entregado)

    # 📅 Filtro por fechas
    if desde:
        try:
            f_desde = datetime.strptime(desde, "%Y-%m-%d")
            query = query.filter(Pedido.fecha_pedido >= f_desde)
        except ValueError:
            pass

    if hasta:
        try:
            f_hasta = datetime.strptime(hasta, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Pedido.fecha_pedido < f_hasta)
        except ValueError:
            pass

    pedidos = query.order_by(Pedido.fecha_pedido.desc()).all()

    return templates.TemplateResponse(
        "pedidos/lista.html",
        {
            "request": request,
            "pedidos": pedidos,
            "buscar": buscar,
            "estado": estado,
            "desde": desde,
            "hasta": hasta,
            "active_page": "pedidos",
        },
    )


@app.get("/pedidos/tablero", response_class=HTMLResponse)
def tablero_pedidos(request: Request, db: Session = Depends(get_db)):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    hoy = date.today()

    base_q = db.query(Pedido).options(joinedload(Pedido.cliente))

    realizados_hoy = (
        base_q
        .filter(
            Pedido.estado == EstadoPedido.pendiente,
            func.date(Pedido.fecha_pedido) == hoy,
        )
        .order_by(Pedido.fecha_pedido.desc())
        .all()
    )

    pendientes = (
        base_q
        .filter(
            Pedido.estado == EstadoPedido.pendiente,
            func.date(Pedido.fecha_pedido) < hoy,
        )
        .order_by(
            Pedido.fecha_entrega.is_(None).desc(),
            Pedido.fecha_entrega,
            Pedido.fecha_pedido,
        )
        .all()
    )

    entregados = (
        base_q
        .filter(Pedido.estado == EstadoPedido.entregado)
        .order_by(
            Pedido.fecha_entrega.desc().nullslast(),
            Pedido.fecha_pedido.desc(),
        )
        .all()
    )

    return templates.TemplateResponse(
        "pedidos/tablero.html",
        {
            "request": request,
            "active_page": "tablero_pedidos",
            "realizados_hoy": realizados_hoy,
            "pendientes": pendientes,
            "entregados": entregados,
            "hoy": hoy,  # <- se usa en la plantilla para marcar atrasados, etc.
        },
    )




@app.post("/pedidos/{pedido_id}/marcar-entregado")
def marcar_pedido_entregado(
    pedido_id: int,
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        return RedirectResponse("/pedidos/tablero", status_code=303)

    pedido.estado = EstadoPedido.entregado
    # Si no tiene fecha de entrega, le ponemos hoy
    if not pedido.fecha_entrega:
        pedido.fecha_entrega = datetime.utcnow().date()
    db.commit()

    return RedirectResponse("/pedidos/tablero", status_code=303)


@app.post("/pedidos/{pedido_id}/eliminar")
def eliminar_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        return RedirectResponse("/pedidos/tablero", status_code=303)

    # Borrar movimiento de cuenta corriente asociado (débito del pedido)
    movs = (
        db.query(MovimientoCtaCte)
        .filter(
            MovimientoCtaCte.descripcion == f"Pedido #{pedido.id}",
            MovimientoCtaCte.tipo == TipoMovimiento.debito,
        )
        .all()
    )
    for m in movs:
        db.delete(m)

    db.delete(pedido)
    db.commit()

    return RedirectResponse("/pedidos/tablero", status_code=303)


@app.get("/pedidos/nuevo", response_class=HTMLResponse)
def nuevo_pedido(
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    clientes = db.query(Cliente).order_by(asc(Cliente.nombre)).all()
    productos = (
        db.query(Producto)
        .filter(Producto.activo == True)
        .order_by(asc(Producto.nombre))
        .all()
    )

    return templates.TemplateResponse(
        "pedidos/form.html",
        {
            "request": request,
            "pedido": None,
            "clientes": clientes,
            "productos": productos,
            "active_page": "pedidos",
        }
    )


@app.get("/pedidos/editar/{pedido_id}", response_class=HTMLResponse)
def editar_pedido(
    pedido_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    pedido = db.get(Pedido, pedido_id)
    clientes = db.query(Cliente).order_by(asc(Cliente.nombre)).all()
    productos = (
        db.query(Producto)
        .filter(Producto.activo == True)
        .order_by(asc(Producto.nombre))
        .all()
    )

    return templates.TemplateResponse(
        "pedidos/form.html",
        {
            "request": request,
            "pedido": pedido,
            "clientes": clientes,
            "productos": productos,
            "active_page": "pedidos",
        }
    )





@app.post("/pedidos/guardar")
async def guardar_pedido(
    request: Request,
    cliente_id: int = Form(...),
    fecha_entrega: str = Form(""),
    medio_contacto: str = Form(""),
    observaciones: str = Form(""),
    descuento: str = Form("0"),   # porcentaje
    producto_id: List[int] = Form(...),
    descripcion_item: List[str] = Form(...),
    cantidad: List[int] = Form(...),
    precio_unitario: List[float] = Form(...),
    db: Session = Depends(get_db),
):
    # Fecha de entrega
    fecha_entrega_dt = None
    if fecha_entrega:
        try:
            fecha_entrega_dt = datetime.strptime(fecha_entrega, "%Y-%m-%d")
        except ValueError:
            fecha_entrega_dt = None

    # Descuento como porcentaje
    try:
        descuento_pct = float((descuento or "0").replace(",", "."))
    except ValueError:
        descuento_pct = 0.0

    pedido = Pedido(
        cliente_id=cliente_id,
        fecha_pedido=datetime.utcnow(),
        fecha_entrega=fecha_entrega_dt,
        medio_contacto=medio_contacto,
        observaciones=observaciones,
        descuento=descuento_pct,           # guardo el porcentaje
        estado=EstadoPedido.pendiente,
    )

    db.add(pedido)
    db.flush()  # para tener pedido.id

    subtotal_pedido = 0.0

    # Ítems
    for idx, prod_id in enumerate(producto_id):
        if not prod_id:
            continue

        prod = db.get(Producto, int(prod_id))
        if not prod:
            continue

        cant = int(cantidad[idx]) if cantidad[idx] else 1
        pv = float(precio_unitario[idx]) if precio_unitario[idx] else prod.precio_venta

        costo = prod.precio_compra
        subtotal = pv * cant
        subtotal_pedido += subtotal

        item = PedidoItem(
            pedido_id=pedido.id,
            producto_id=prod.id,
            descripcion_item=descripcion_item[idx] or prod.nombre,
            cantidad=cant,
            precio_venta_unitario=pv,
            costo_unitario=costo,
            subtotal=subtotal,
        )
        db.add(item)

    if pedido.descuento is None:
        pedido.descuento = 0.0

    # Descuento en monto a partir del porcentaje
    descuento_monto = subtotal_pedido * (pedido.descuento / 100.0)
    pedido.total = max(subtotal_pedido - descuento_monto, 0.0)

    # Movimiento cta cte por el TOTAL NETO
    if pedido.total > 0:
        mov = MovimientoCtaCte(
            cliente_id=pedido.cliente_id,
            tipo=TipoMovimiento.debito,
            monto=pedido.total,
            descripcion=f"Pedido #{pedido.id}",
        )
        db.add(mov)

    db.commit()

    return RedirectResponse("/pedidos", status_code=303)


@app.get("/pedidos/ver/{pedido_id}", response_class=HTMLResponse)
def ver_pedido(
    pedido_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    pedido = (
        db.query(Pedido)
        .options(
            joinedload(Pedido.items).joinedload(PedidoItem.producto),
            joinedload(Pedido.cliente),
        )
        .filter(Pedido.id == pedido_id)
        .first()
    )

    if not pedido:
        # Si el ID no existe, volvemos al listado
        return RedirectResponse("/pedidos", status_code=303)

    # Calcular subtotal / descuentos / total
    subtotal = sum((item.subtotal or 0.0) for item in pedido.items)
    desc_pct = pedido.descuento or 0.0
    desc_monto = subtotal * (desc_pct / 100.0)
    total = pedido.total or max(subtotal - desc_monto, 0.0)

    return templates.TemplateResponse(
        "pedidos/ver.html",
        {
            "request": request,
            "pedido": pedido,
            "subtotal": subtotal,
            "descuento_pct": desc_pct,
            "descuento_monto": desc_monto,
            "total": total,
            "active_page": "pedidos",
        }
    )


@app.post("/pedidos/{pedido_id}/eliminar")
def eliminar_pedido(
    pedido_id: int,
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        return RedirectResponse("/pedidos/tablero", status_code=303)

    # Borrar movimiento de cuenta corriente asociado (el débito del pedido)
    movs = (
        db.query(MovimientoCtaCte)
        .filter(
            MovimientoCtaCte.descripcion == f"Pedido #{pedido.id}",
            MovimientoCtaCte.tipo == TipoMovimiento.debito,
        )
        .all()
    )
    for m in movs:
        db.delete(m)

    # Borrar ítems y pedido (cascade ya maneja los ítems)
    db.delete(pedido)
    db.commit()

    return RedirectResponse("/pedidos/tablero", status_code=303)



@app.post("/pedidos/actualizar/{pedido_id}")
async def actualizar_pedido(
    pedido_id: int,
    cliente_id: int = Form(...),
    fecha_entrega: str = Form(""),
    medio_contacto: str = Form(""),
    observaciones: str = Form(""),
    descuento: str = Form("0"),   # porcentaje
    producto_id: List[int] = Form(...),
    descripcion_item: List[str] = Form(...),
    cantidad: List[int] = Form(...),
    precio_unitario: List[float] = Form(...),
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)

    # Fecha
    fecha_entrega_dt = None
    if fecha_entrega:
        try:
            fecha_entrega_dt = datetime.strptime(fecha_entrega, "%Y-%m-%d")
        except ValueError:
            fecha_entrega_dt = None

    # Descuento como porcentaje
    try:
        descuento_pct = float((descuento or "0").replace(",", "."))
    except ValueError:
        descuento_pct = 0.0

    pedido.cliente_id = cliente_id
    pedido.fecha_entrega = fecha_entrega_dt
    pedido.medio_contacto = medio_contacto
    pedido.observaciones = observaciones
    pedido.descuento = descuento_pct

    # Borrar ítems anteriores
    for item in list(pedido.items):
        db.delete(item)
    db.flush()

    subtotal_pedido = 0.0

    # Re-crear ítems
    for idx, prod_id in enumerate(producto_id):
        if not prod_id:
            continue

        prod = db.get(Producto, int(prod_id))
        if not prod:
            continue

        cant = int(cantidad[idx]) if cantidad[idx] else 1
        pv = float(precio_unitario[idx]) if precio_unitario[idx] else prod.precio_venta

        costo = prod.precio_compra
        subtotal = pv * cant
        subtotal_pedido += subtotal

        item = PedidoItem(
            pedido_id=pedido.id,
            producto_id=prod.id,
            descripcion_item=descripcion_item[idx] or prod.nombre,
            cantidad=cant,
            precio_venta_unitario=pv,
            costo_unitario=costo,
            subtotal=subtotal,
        )
        db.add(item)

    if pedido.descuento is None:
        pedido.descuento = 0.0

    descuento_monto = subtotal_pedido * (pedido.descuento / 100.0)
    pedido.total = max(subtotal_pedido - descuento_monto, 0.0)

    # Actualizar movimiento de cta cte
    mov = (
        db.query(MovimientoCtaCte)
        .filter(
            MovimientoCtaCte.descripcion == f"Pedido #{pedido.id}",
            MovimientoCtaCte.tipo == TipoMovimiento.debito,
        )
        .order_by(desc(MovimientoCtaCte.fecha))
        .first()
    )

    if pedido.total > 0:
        if mov:
            mov.cliente_id = pedido.cliente_id
            mov.monto = pedido.total
        else:
            mov = MovimientoCtaCte(
                cliente_id=pedido.cliente_id,
                tipo=TipoMovimiento.debito,
                monto=pedido.total,
                descripcion=f"Pedido #{pedido.id}",
            )
            db.add(mov)
    else:
        if mov:
            db.delete(mov)

    db.commit()

    return RedirectResponse("/pedidos", status_code=303)



@app.post("/pedidos/{pedido_id}/marcar-entregado")
def marcar_pedido_entregado(
    pedido_id: int,
    db: Session = Depends(get_db),
):
    pedido = db.get(Pedido, pedido_id)
    if pedido:
        pedido.estado = EstadoPedido.entregado
        pedido.fecha_entrega = datetime.utcnow()
        db.commit()

    return RedirectResponse("/pedidos/tablero", status_code=303)


# =========================
# USUARIOS (ADMIN)
# =========================

def require_admin(request: Request):
    if not is_logged_in(request):
        return False
    user = request.session.get("user")
    return bool(user and user.get("es_admin"))


@app.get("/usuarios", response_class=HTMLResponse)
def listar_usuarios(
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse("/", status_code=303)

    usuarios = db.query(Usuario).order_by(asc(Usuario.username)).all()
    return templates.TemplateResponse(
        "usuarios/lista.html",
        {
            "request": request,
            "usuarios": usuarios,
            "active_page": "usuarios",
        }
    )


@app.get("/usuarios/nuevo", response_class=HTMLResponse)
def nuevo_usuario(request: Request):
    if not require_admin(request):
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse(
        "usuarios/form.html",
        {
            "request": request,
            "usuario": None,
            "error": None,
            "active_page": "usuarios",
        }
    )


@app.post("/usuarios/guardar")
def guardar_usuario(
    request: Request,
    username: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    es_admin: bool = Form(False),
    activo: bool = Form(True),
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse("/", status_code=303)

    existing = db.query(Usuario).filter(Usuario.username == username).first()
    if existing:
        return templates.TemplateResponse(
            "usuarios/form.html",
            {
                "request": request,
                "usuario": None,
                "error": "Ya existe un usuario con ese nombre de usuario.",
                "active_page": "usuarios",
            }
        )

    usuario = Usuario(
        username=username,
        nombre=nombre,
        es_admin=es_admin,
        activo=activo,
        password_hash=hash_password(password),
    )
    db.add(usuario)
    db.commit()

    return RedirectResponse("/usuarios", status_code=303)


@app.get("/usuarios/editar/{usuario_id}", response_class=HTMLResponse)
def editar_usuario(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse("/", status_code=303)

    usuario = db.get(Usuario, usuario_id)

    return templates.TemplateResponse(
        "usuarios/form.html",
        {
            "request": request,
            "usuario": usuario,
            "error": None,
            "active_page": "usuarios",
        }
    )


@app.post("/usuarios/actualizar/{usuario_id}")
def actualizar_usuario(
    usuario_id: int,
    request: Request,
    username: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(""),
    es_admin: bool = Form(False),
    activo: bool = Form(True),
    db: Session = Depends(get_db),
):
    if not require_admin(request):
        return RedirectResponse("/", status_code=303)

    usuario = db.get(Usuario, usuario_id)

    # Validar username único
    existing = (
        db.query(Usuario)
        .filter(Usuario.username == username, Usuario.id != usuario_id)
        .first()
    )
    if existing:
        return templates.TemplateResponse(
            "usuarios/form.html",
            {
                "request": request,
                "usuario": usuario,
                "error": "Ya existe otro usuario con ese nombre de usuario.",
                "active_page": "usuarios",
            }
        )

    usuario.username = username
    usuario.nombre = nombre
    usuario.es_admin = es_admin
    usuario.activo = activo

    if password:
        usuario.password_hash = hash_password(password)

    db.commit()

    return RedirectResponse("/usuarios", status_code=303)

@app.post("/clientes/{cliente_id}/registrar-pago")
def registrar_pago(
    cliente_id: int,
    monto: float = Form(...),
    descripcion: str = Form("Pago"),
    db: Session = Depends(get_db),
):
    pago = MovimientoCtaCte(
        cliente_id=cliente_id,
        tipo=TipoMovimiento.credito,
        monto=monto,
        descripcion=descripcion,
    )
    db.add(pago)
    db.commit()
    return RedirectResponse(
        f"/clientes/{cliente_id}/cta-cte",
        status_code=303,
    )


# =========================
# REPORTES
# =========================

@app.get("/reportes", response_class=HTMLResponse)
def reportes(
    request: Request,
    desde: str = "",
    hasta: str = "",
    db: Session = Depends(get_db),
):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=303)

    hoy = date.today()

    # Rango por defecto: últimos 30 días
    if not desde:
        desde_date = hoy - timedelta(days=30)
    else:
        try:
            desde_date = datetime.strptime(desde, "%Y-%m-%d").date()
        except ValueError:
            desde_date = hoy - timedelta(days=30)

    if not hasta:
        hasta_date = hoy
    else:
        try:
            hasta_date = datetime.strptime(hasta, "%Y-%m-%d").date()
        except ValueError:
            hasta_date = hoy

    # Para comparar con DateTime
    inicio = datetime.combine(desde_date, datetime.min.time())
    fin = datetime.combine(hasta_date + timedelta(days=1), datetime.min.time())

    # Traigo pedidos con items y cliente
    pedidos = (
        db.query(Pedido)
        .options(
            joinedload(Pedido.items).joinedload(PedidoItem.producto),
            joinedload(Pedido.cliente),
        )
        .filter(Pedido.fecha_pedido >= inicio,
                Pedido.fecha_pedido < fin)
        .all()
    )

    # Acumuladores globales
    total_ventas = 0.0
    total_descuentos = 0.0
    total_ganancia = 0.0

    # Detalle por día: {fecha: {pedidos, ventas, descuentos, ganancia}}
    detalle_dias: dict[date, dict] = {}

    # Ranking clientes: {cliente_id: {nombre, ventas, ganancia, pedidos}}
    ranking_clientes: dict[int, dict] = {}

    # Ranking productos: {producto_id: {nombre, unidades, ventas, ganancia}}
    ranking_productos: dict[int, dict] = {}

    for p in pedidos:
        # Subtotal del pedido y costo
        subtotal = 0.0
        costo_total = 0.0

        for item in p.items:
            # Por las dudas, recalculo subtotal si está en None
            item_sub = item.subtotal or (item.precio_venta_unitario * item.cantidad)
            subtotal += item_sub
            costo_total += (item.costo_unitario or 0) * item.cantidad

        # Descuento en porcentaje guardado en el pedido
        desc_pct = p.descuento or 0.0
        desc_monto = subtotal * (desc_pct / 100.0)
        venta_neta = subtotal - desc_monto
        ganancia = venta_neta - costo_total

        total_ventas += venta_neta
        total_descuentos += desc_monto
        total_ganancia += ganancia

        # ---------------- DETALLE POR DÍA ----------------
        f = p.fecha_pedido.date()
        if f not in detalle_dias:
            detalle_dias[f] = {
                "pedidos": 0,
                "ventas": 0.0,
                "descuentos": 0.0,
                "ganancia": 0.0,
            }
        detalle_dias[f]["pedidos"] += 1
        detalle_dias[f]["ventas"] += venta_neta
        detalle_dias[f]["descuentos"] += desc_monto
        detalle_dias[f]["ganancia"] += ganancia

        # ---------------- RANKING CLIENTES ----------------
        if p.cliente:
            cid = p.cliente.id
            if cid not in ranking_clientes:
                ranking_clientes[cid] = {
                    "nombre": p.cliente.nombre,
                    "ventas": 0.0,
                    "ganancia": 0.0,
                    "pedidos": 0,
                }
            ranking_clientes[cid]["ventas"] += venta_neta
            ranking_clientes[cid]["ganancia"] += ganancia
            ranking_clientes[cid]["pedidos"] += 1

        # ---------------- RANKING PRODUCTOS ----------------
        # Reparto el descuento del pedido proporcional a cada item
        for item in p.items:
            item_sub = item.subtotal or (item.precio_venta_unitario * item.cantidad)
            if subtotal > 0:
                item_desc = desc_monto * (item_sub / subtotal)
            else:
                item_desc = 0.0

            item_venta_neta = item_sub - item_desc
            item_ganancia = item_venta_neta - (item.costo_unitario or 0) * item.cantidad

            if item.producto:
                pid = item.producto.id
                if pid not in ranking_productos:
                    ranking_productos[pid] = {
                        "nombre": item.producto.nombre,
                        "unidades": 0,
                        "ventas": 0.0,
                        "ganancia": 0.0,
                    }
                ranking_productos[pid]["unidades"] += item.cantidad
                ranking_productos[pid]["ventas"] += item_venta_neta
                ranking_productos[pid]["ganancia"] += item_ganancia

    # Rentabilidad global
    rentabilidad_pct = (total_ganancia / total_ventas * 100.0) if total_ventas > 0 else 0.0

    # Transformo detalle_dias en lista ordenada por fecha descendente
    detalle_dias_lista = []
    for f, datos in detalle_dias.items():
        ventas_dia = datos["ventas"]
        ganancia_dia = datos["ganancia"]
        rentab_dia = (ganancia_dia / ventas_dia * 100.0) if ventas_dia > 0 else 0.0
        detalle_dias_lista.append({
            "fecha": f,
            "pedidos": datos["pedidos"],
            "ventas": ventas_dia,
            "descuentos": datos["descuentos"],
            "ganancia": ganancia_dia,
            "rentabilidad": rentab_dia,
        })
    detalle_dias_lista.sort(key=lambda x: x["fecha"], reverse=True)

    # Top 5 clientes y productos
    top_clientes = sorted(
        ranking_clientes.values(),
        key=lambda x: x["ventas"],
        reverse=True
    )[:5]

    top_productos = sorted(
        ranking_productos.values(),
        key=lambda x: x["ventas"],
        reverse=True
    )[:5]

    return templates.TemplateResponse(
        "reportes/dashboard.html",
        {
            "request": request,
            "desde": desde_date.strftime("%Y-%m-%d"),
            "hasta": hasta_date.strftime("%Y-%m-%d"),
            "total_ventas": total_ventas,
            "total_descuentos": total_descuentos,
            "total_ganancia": total_ganancia,
            "rentabilidad_pct": rentabilidad_pct,
            "detalle_dias": detalle_dias_lista,
            "top_clientes": top_clientes,
            "top_productos": top_productos,
            "active_page": "reportes",
        },
    )


@app.get("/reportes/exportar")
def exportar_reportes(
    request: Request,
    desde: str = "",
    hasta: str = "",
    db: Session = Depends(get_db),
):
    hoy = date.today()

    if not desde:
        desde_date = hoy - timedelta(days=30)
    else:
        try:
            desde_date = datetime.strptime(desde, "%Y-%m-%d").date()
        except ValueError:
            desde_date = hoy - timedelta(days=30)

    if not hasta:
        hasta_date = hoy
    else:
        try:
            hasta_date = datetime.strptime(hasta, "%Y-%m-%d").date()
        except ValueError:
            hasta_date = hoy

    inicio = datetime.combine(desde_date, datetime.min.time())
    fin = datetime.combine(hasta_date + timedelta(days=1), datetime.min.time())

    pedidos = (
        db.query(Pedido)
        .options(joinedload(Pedido.items))
        .filter(Pedido.fecha_pedido >= inicio,
                Pedido.fecha_pedido < fin)
        .all()
    )

    # Armo detalle por día igual que en el dashboard
    detalle_dias = {}

    for p in pedidos:
        subtotal = 0.0
        costo_total = 0.0
        for item in p.items:
            item_sub = item.subtotal or (item.precio_venta_unitario * item.cantidad)
            subtotal += item_sub
            costo_total += (item.costo_unitario or 0) * item.cantidad

        desc_pct = p.descuento or 0.0
        desc_monto = subtotal * (desc_pct / 100.0)
        venta_neta = subtotal - desc_monto
        ganancia = venta_neta - costo_total

        f = p.fecha_pedido.date()
        if f not in detalle_dias:
            detalle_dias[f] = {
                "pedidos": 0,
                "ventas": 0.0,
                "descuentos": 0.0,
                "ganancia": 0.0,
            }
        detalle_dias[f]["pedidos"] += 1
        detalle_dias[f]["ventas"] += venta_neta
        detalle_dias[f]["descuentos"] += desc_monto
        detalle_dias[f]["ganancia"] += ganancia

    filas = []
    for f, datos in detalle_dias.items():
        ventas = datos["ventas"]
        gan = datos["ganancia"]
        rent = (gan / ventas * 100.0) if ventas > 0 else 0.0
        filas.append([
            f.strftime("%d/%m/%Y"),
            datos["pedidos"],
            f"{ventas:.2f}",
            f"{datos['descuentos']:.2f}",
            f"{gan:.2f}",
            f"{rent:.2f}",
        ])

    filas.sort(key=lambda r: datetime.strptime(r[0], "%d/%m/%Y"), reverse=True)

    # Genero CSV en memoria
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Fecha", "Pedidos", "Ventas", "Descuentos", "Ganancia", "Rentabilidad %"])
    for row in filas:
        writer.writerow(row)

    output.seek(0)

    filename = f"reportes_{desde_date.strftime('%Y%m%d')}_{hasta_date.strftime('%Y%m%d')}.csv"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================================
# wc3-classic-revival — targets de operacion
# Los targets que tocan el sistema (bootstrap/build/install/render) piden sudo
# y solo tienen sentido en el VPS; validate y map-scan corren en cualquier lado.
# ============================================================================

.PHONY: help bootstrap build install render-config validate map-scan test backup \
	lobby-names brand-maps kit recibir dashboard

# install = bootstrap + build + mysql, EN ORDEN: con make -j los prerequisitos
# correrian en paralelo y el build arrancaria sin las dependencias del bootstrap.
.NOTPARALLEL:

help:
	@echo "Targets:"
	@echo "  bootstrap      prepara un Ubuntu 24.04 limpio (sudo)"
	@echo "  build          compila e instala PvPGN y Aura (sudo)"
	@echo "  install        bootstrap + build + mysql (sudo)"
	@echo "  render-config  renderiza templates + .env -> configs (sudo)"
	@echo "  validate       valida todo en seco (sin VPS ni juego)"
	@echo "  test           tests de inspect-map.py"
	@echo "  map-scan       inspecciona todos los .w3x de maps/ y actualiza el registry"
	@echo "  dashboard      instala/prende el panel web de admin, permanente (sudo)"
	@echo "  recibir        abre una pagina web para subir mapas desde el navegador (sudo)"
	@echo "  kit            arma dist/<realm>-Kit.zip para repartir a los amigos"
	@echo "  lobby-names    chuleta de nombres de partida con color, para pegar"
	@echo "  brand-maps     mete la preview propia a los .w3x de /opt/wc3/incoming"
	@echo "  backup         dump de MySQL + configs a tar fechado (sudo)"

bootstrap:
	sudo ./install/00-bootstrap-vps.sh

build:
	sudo ./install/10-build-pvpgn.sh
	sudo ./install/20-build-hostbot.sh

install: bootstrap build
	sudo ./install/30-setup-mysql.sh

render-config:
	sudo ./install/40-render-configs.sh

validate:
	./scripts/validate.sh

test:
	python3 -m unittest discover -s tests -v

# Usa el venv del VPS si existe (tiene mpyq); si no, el python del sistema
# (solo header HM3W). El || true: un mapa protegido (exit 2) no corta el scan.
map-scan:
	@PY=/opt/wc3/venv/bin/python; [ -x $$PY ] || PY=python3; \
	found=0; \
	for m in maps/*.w3x /opt/wc3/maps/*.w3x; do \
		[ -f "$$m" ] || continue; \
		found=1; \
		echo "== $$m"; \
		$$PY scripts/inspect-map.py "$$m" --update-registry --pretty || true; \
	done; \
	[ $$found -eq 1 ] || echo "no hay .w3x en maps/ ni /opt/wc3/maps/"

# Los mapas se incluyen si estan en /opt/wc3/maps (los ya "brandeados").
kit:
	@if [ -d /opt/wc3/maps ]; then \
		./scripts/build-kit.sh --maps /opt/wc3/maps; \
	else \
		./scripts/build-kit.sh; \
	fi

# Sirve para no pelear con scp: se abre la URL que imprime y se arrastran
# los .w3x. El puerto se abre y se cierra solo.
recibir:
	sudo ./scripts/recibir-mapas.sh

# Panel web de admin permanente: estado de servicios, jugadores conectados,
# mapas, backups, disco, y subida de mapas. Ver docs/dashboard.md.
dashboard:
	sudo ./install/60-setup-dashboard.sh

lobby-names:
	@PY=/opt/wc3/venv/bin/python; [ -x $$PY ] || PY=python3; \
	$$PY scripts/lobby-names.py

# Los .w3x nuevos se suben a /opt/wc3/incoming; esto les mete la preview y los
# deja en /opt/wc3/maps. Los originales quedan donde estaban.
brand-maps:
	@PY=/opt/wc3/venv/bin/python; [ -x $$PY ] || PY=python3; \
	found=0; \
	for m in /opt/wc3/incoming/*.w3x; do \
		[ -f "$$m" ] || continue; found=1; \
	done; \
	if [ $$found -eq 0 ]; then \
		echo "no hay .w3x en /opt/wc3/incoming (subilos ahi primero)"; \
	else \
		sudo $$PY scripts/brand-map.py /opt/wc3/incoming/*.w3x --out-dir /opt/wc3/maps && \
		sudo chown wc3:wc3 /opt/wc3/maps/*.w3x; \
	fi

backup:
	sudo ./scripts/backup.sh

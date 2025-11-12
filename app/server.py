import datetime as dt
import json
import posixpath
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

from .auth import create_session, delete_session, get_user_by_token
from .db import get_connection, init_db, seed_if_empty

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "SUPServer/1.0"

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    # Utilities --------------------------------------------------
    def parse_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        data = self.rfile.read(length)
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, payload: str, status: int = HTTPStatus.OK, content_type: str = "text/plain; charset=utf-8") -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def current_user(self) -> Optional[Dict[str, Any]]:
        auth = self.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        return get_user_by_token(token)

    def require_user(self, roles: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        user = self.current_user()
        if not user:
            self.send_json({"detail": "Unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return None
        if roles and user["role"] not in roles:
            self.send_json({"detail": "Forbidden"}, status=HTTPStatus.FORBIDDEN)
            return None
        return user

    # HTTP Methods ------------------------------------------------
    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self.handle_api_get()
        else:
            self.serve_static()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self.handle_api_post()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        if self.path.startswith("/api/"):
            self.handle_api_put()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        if self.path.startswith("/api/"):
            self.handle_api_delete()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    # Static serving ----------------------------------------------
    def translate_path(self, path: str) -> Path:
        path = path.split("?", 1)[0]
        path = path.split("#", 1)[0]
        trailing = posixpath.normpath(urllib.parse.unquote(path))
        if trailing.startswith("../"):
            trailing = "/"
        rel = trailing.lstrip("/")
        full = STATIC_DIR / rel
        if full.is_dir():
            full = full / "index.html"
        return full

    def serve_static(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        file_path = self.translate_path(path)
        if path == "/" and INDEX_FILE.exists():
            file_path = INDEX_FILE
        if file_path.exists() and file_path.is_file():
            content_type = guess_content_type(file_path)
            with open(file_path, "rb") as fh:
                data = fh.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    # API routing -------------------------------------------------
    def handle_api_get(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/ping":
            self.send_json({"status": "ok"})
            return

        if path == "/api/dashboard":
            user = self.require_user()
            if not user:
                return
            payload = build_dashboard()
            self.send_json(payload)
            return

        if path == "/api/personnel":
            user = self.require_user()
            if not user:
                return
            self.send_json(list_personnel())
            return

        if path == "/api/duty-types":
            user = self.require_user()
            if not user:
                return
            self.send_json(list_duty_types())
            return

        if path == "/api/equipment":
            user = self.require_user()
            if not user:
                return
            category = query.get("category", [None])[0]
            self.send_json(list_equipment(category))
            return

        if path == "/api/schedule":
            user = self.require_user()
            if not user:
                return
            month = query.get("month", [None])[0]
            self.send_json(get_schedule(month))
            return

        if path == "/api/plan":
            user = self.require_user()
            if not user:
                return
            date = query.get("date", [None])[0]
            self.send_json(get_plan(date))
            return

        if path == "/api/vacations":
            user = self.require_user()
            if not user:
                return
            self.send_json(list_vacations())
            return

        if path == "/api/analytics/summary":
            user = self.require_user()
            if not user:
                return
            start = query.get("start", [None])[0]
            end = query.get("end", [None])[0]
            self.send_json(get_summary(start, end))
            return

        if path == "/api/auth/me":
            user = self.current_user()
            if not user:
                self.send_json({"authenticated": False})
            else:
                self.send_json({"authenticated": True, "username": user["username"], "role": user["role"]})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_api_post(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/auth/login":
            data = self.parse_json_body()
            session = create_session(data.get("username", ""), data.get("password", ""))
            if not session:
                self.send_json({"detail": "Невірні облікові дані"}, status=HTTPStatus.UNAUTHORIZED)
            else:
                self.send_json(session)
            return

        if path == "/api/auth/logout":
            user = self.require_user()
            if not user:
                return
            token = user["token"]
            delete_session(token)
            self.send_json({"detail": "Вихід виконано"})
            return

        if path == "/api/personnel":
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            data = self.parse_json_body()
            created = create_personnel(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": "Некоректні дані"}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/duty-types":
            user = self.require_user(["admin"])
            if not user:
                return
            data = self.parse_json_body()
            created = create_duty_type(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": "Некоректні дані"}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/equipment":
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            data = self.parse_json_body()
            created = create_equipment(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": "Некоректні дані"}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/schedule":
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            data = self.parse_json_body()
            created, error = upsert_schedule_entry(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": error or "Помилка збереження"}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/plan":
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            data = self.parse_json_body()
            created, error = create_plan_entry(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": error or "Помилка збереження"}, status=HTTPStatus.BAD_REQUEST)
            return

        if path == "/api/vacations":
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            data = self.parse_json_body()
            created, error = create_vacation(data)
            if created:
                self.send_json(created, status=HTTPStatus.CREATED)
            else:
                self.send_json({"detail": error or "Помилка збереження"}, status=HTTPStatus.BAD_REQUEST)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_api_put(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/personnel/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            person_id = path.split("/")[-1]
            data = self.parse_json_body()
            updated = update_personnel(person_id, data)
            if updated:
                self.send_json(updated)
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/duty-types/"):
            user = self.require_user(["admin"])
            if not user:
                return
            type_id = path.split("/")[-1]
            data = self.parse_json_body()
            updated = update_duty_type(type_id, data)
            if updated:
                self.send_json(updated)
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/equipment/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            equipment_id = path.split("/")[-1]
            data = self.parse_json_body()
            updated = update_equipment(equipment_id, data)
            if updated:
                self.send_json(updated)
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/plan/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            plan_id = path.split("/")[-1]
            data = self.parse_json_body()
            updated, error = update_plan_entry(plan_id, data)
            if updated:
                self.send_json(updated)
            else:
                self.send_json({"detail": error or "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/vacations/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            vacation_id = path.split("/")[-1]
            data = self.parse_json_body()
            updated, error = update_vacation(vacation_id, data)
            if updated:
                self.send_json(updated)
            else:
                self.send_json({"detail": error or "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_api_delete(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/personnel/"):
            user = self.require_user(["admin"])
            if not user:
                return
            person_id = path.split("/")[-1]
            if delete_personnel(person_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/duty-types/"):
            user = self.require_user(["admin"])
            if not user:
                return
            type_id = path.split("/")[-1]
            if delete_duty_type(type_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/equipment/"):
            user = self.require_user(["admin"])
            if not user:
                return
            equipment_id = path.split("/")[-1]
            if delete_equipment(equipment_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/schedule/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            entry_id = path.split("/")[-1]
            if delete_schedule_entry(entry_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/plan/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            entry_id = path.split("/")[-1]
            if delete_plan_entry(entry_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        if path.startswith("/api/vacations/"):
            user = self.require_user(["admin", "planner"])
            if not user:
                return
            entry_id = path.split("/")[-1]
            if delete_vacation(entry_id):
                self.send_json({"detail": "Видалено"})
            else:
                self.send_json({"detail": "Не знайдено"}, status=HTTPStatus.NOT_FOUND)
            return

        self.send_error(HTTPStatus.NOT_FOUND)


# Database helpers -------------------------------------------------


def list_personnel() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM personnel ORDER BY unit, full_name")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def sanitize_payload(data: Dict[str, Any], integer_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    integer_fields = integer_fields or []
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        if key in integer_fields:
            try:
                value = int(value) if value is not None else None
            except (TypeError, ValueError):
                value = None
        cleaned[key] = value
    return cleaned


def create_personnel(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    required = ["full_name", "role", "unit"]
    if not all(data.get(field) for field in required):
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO personnel (full_name, role, callsign, unit) VALUES (?, ?, ?, ?)",
        (data["full_name"], data["role"], data.get("callsign"), data["unit"]),
    )
    conn.commit()
    person_id = cur.lastrowid
    cur.execute("SELECT * FROM personnel WHERE id = ?", (person_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def update_personnel(person_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM personnel WHERE id = ?", (person_id,))
    if not cur.fetchone():
        conn.close()
        return None
    cur.execute(
        "UPDATE personnel SET full_name = ?, role = ?, callsign = ?, unit = ? WHERE id = ?",
        (
            data.get("full_name"),
            data.get("role"),
            data.get("callsign"),
            data.get("unit"),
            person_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM personnel WHERE id = ?", (person_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def delete_personnel(person_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM personnel WHERE id = ?", (person_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_duty_types() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM duty_types ORDER BY code")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def create_duty_type(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    required = ["code", "name", "color"]
    if not all(data.get(field) for field in required):
        return None
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO duty_types (code, name, color, description, blocks_availability) VALUES (?, ?, ?, ?, ?)",
            (
                data["code"],
                data["name"],
                data["color"],
                data.get("description"),
                1 if data.get("blocks_availability") else 0,
            ),
        )
    except Exception:
        conn.close()
        return None
    conn.commit()
    duty_id = cur.lastrowid
    cur.execute("SELECT * FROM duty_types WHERE id = ?", (duty_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def update_duty_type(type_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM duty_types WHERE id = ?", (type_id,))
    if not cur.fetchone():
        conn.close()
        return None
    cur.execute(
        "UPDATE duty_types SET code = ?, name = ?, color = ?, description = ?, blocks_availability = ? WHERE id = ?",
        (
            data.get("code"),
            data.get("name"),
            data.get("color"),
            data.get("description"),
            1 if data.get("blocks_availability") else 0,
            type_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM duty_types WHERE id = ?", (type_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def delete_duty_type(type_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM duty_types WHERE id = ?", (type_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_equipment(category: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT * FROM equipment WHERE category = ? ORDER BY name", (category,))
    else:
        cur.execute("SELECT * FROM equipment ORDER BY category, name")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def create_equipment(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    required = ["name", "category"]
    if not all(data.get(field) for field in required):
        return None
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO equipment (name, category) VALUES (?, ?)",
            (data["name"], data["category"]),
        )
    except Exception:
        conn.close()
        return None
    conn.commit()
    equipment_id = cur.lastrowid
    cur.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def update_equipment(equipment_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = sanitize_payload(data)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
    if not cur.fetchone():
        conn.close()
        return None
    cur.execute(
        "UPDATE equipment SET name = ?, category = ? WHERE id = ?",
        (data.get("name"), data.get("category"), equipment_id),
    )
    conn.commit()
    cur.execute("SELECT * FROM equipment WHERE id = ?", (equipment_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


def delete_equipment(equipment_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM equipment WHERE id = ?", (equipment_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_schedule(month: Optional[str]) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    if month:
        start = f"{month}-01"
        end_date = dt.datetime.strptime(start, "%Y-%m-%d")
        next_month = (end_date.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        end = (next_month - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        cur.execute(
            "SELECT schedule_entries.*, personnel.full_name, duty_types.code, duty_types.color FROM schedule_entries "
            "JOIN personnel ON personnel.id = schedule_entries.person_id "
            "JOIN duty_types ON duty_types.id = schedule_entries.duty_type_id "
            "WHERE duty_date BETWEEN ? AND ? ORDER BY duty_date, full_name",
            (start, end),
        )
    else:
        cur.execute(
            "SELECT schedule_entries.*, personnel.full_name, duty_types.code, duty_types.color FROM schedule_entries "
            "JOIN personnel ON personnel.id = schedule_entries.person_id "
            "JOIN duty_types ON duty_types.id = schedule_entries.duty_type_id ORDER BY duty_date DESC LIMIT 200",
        )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"entries": rows}


def upsert_schedule_entry(data: Dict[str, Any]) -> (Optional[Dict[str, Any]], Optional[str]):
    data = sanitize_payload(data, ["person_id", "duty_type_id"])
    required = ["duty_date", "person_id", "duty_type_id"]
    if not all(data.get(field) for field in required):
        return None, "Обов'язкові поля відсутні"

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO schedule_entries (duty_date, person_id, duty_type_id, note) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(duty_date, person_id) DO UPDATE SET duty_type_id = excluded.duty_type_id, note = excluded.note",
            (
                data["duty_date"],
                data["person_id"],
                data["duty_type_id"],
                data.get("note"),
            ),
        )
    except Exception as exc:
        conn.close()
        return None, str(exc)
    conn.commit()
    cur.execute(
        "SELECT schedule_entries.*, personnel.full_name, duty_types.code, duty_types.color FROM schedule_entries "
        "JOIN personnel ON personnel.id = schedule_entries.person_id "
        "JOIN duty_types ON duty_types.id = schedule_entries.duty_type_id WHERE schedule_entries.duty_date = ? AND schedule_entries.person_id = ?",
        (data["duty_date"], data["person_id"]),
    )
    row = dict(cur.fetchone())
    conn.close()
    return row, None


def delete_schedule_entry(entry_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM schedule_entries WHERE id = ?", (entry_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_plan(date: Optional[str]) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    if date:
        cur.execute(
            "SELECT plan_entries.*, pilot.full_name AS pilot_name, navigator.full_name AS navigator_name, "
            "uav.name AS uav_name, vehicle.name AS vehicle_name, battery.name AS battery_name "
            "FROM plan_entries "
            "LEFT JOIN personnel AS pilot ON pilot.id = plan_entries.pilot_id "
            "LEFT JOIN personnel AS navigator ON navigator.id = plan_entries.navigator_id "
            "LEFT JOIN equipment AS uav ON uav.id = plan_entries.uav_id "
            "LEFT JOIN equipment AS vehicle ON vehicle.id = plan_entries.vehicle_id "
            "LEFT JOIN equipment AS battery ON battery.id = plan_entries.battery_id "
            "WHERE plan_date = ? ORDER BY start_time",
            (date,),
        )
    else:
        cur.execute(
            "SELECT plan_entries.*, pilot.full_name AS pilot_name, navigator.full_name AS navigator_name, "
            "uav.name AS uav_name, vehicle.name AS vehicle_name, battery.name AS battery_name "
            "FROM plan_entries "
            "LEFT JOIN personnel AS pilot ON pilot.id = plan_entries.pilot_id "
            "LEFT JOIN personnel AS navigator ON navigator.id = plan_entries.navigator_id "
            "LEFT JOIN equipment AS uav ON uav.id = plan_entries.uav_id "
            "LEFT JOIN equipment AS vehicle ON vehicle.id = plan_entries.vehicle_id "
            "LEFT JOIN equipment AS battery ON battery.id = plan_entries.battery_id "
            "ORDER BY plan_date DESC, start_time",
        )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"entries": rows}


def create_plan_entry(data: Dict[str, Any]) -> (Optional[Dict[str, Any]], Optional[str]):
    data = sanitize_payload(
        data,
        [
            "pilot_id",
            "navigator_id",
            "uav_id",
            "vehicle_id",
            "battery_id",
        ],
    )
    required = ["plan_date", "unit", "mission"]
    if not all(data.get(field) for field in required):
        return None, "Відсутні обов'язкові поля"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO plan_entries (plan_date, unit, mission, start_time, end_time, pilot_id, navigator_id, uav_id, vehicle_id, battery_id, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data["plan_date"],
            data["unit"],
            data["mission"],
            data.get("start_time"),
            data.get("end_time"),
            data.get("pilot_id"),
            data.get("navigator_id"),
            data.get("uav_id"),
            data.get("vehicle_id"),
            data.get("battery_id"),
            data.get("notes"),
        ),
    )
    conn.commit()
    plan_id = cur.lastrowid
    cur.execute("SELECT * FROM plan_entries WHERE id = ?", (plan_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row, None


def update_plan_entry(plan_id: str, data: Dict[str, Any]) -> (Optional[Dict[str, Any]], Optional[str]):
    data = sanitize_payload(
        data,
        [
            "pilot_id",
            "navigator_id",
            "uav_id",
            "vehicle_id",
            "battery_id",
        ],
    )
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM plan_entries WHERE id = ?", (plan_id,))
    if not cur.fetchone():
        conn.close()
        return None, "Не знайдено"
    cur.execute(
        "UPDATE plan_entries SET plan_date = ?, unit = ?, mission = ?, start_time = ?, end_time = ?, "
        "pilot_id = ?, navigator_id = ?, uav_id = ?, vehicle_id = ?, battery_id = ?, notes = ? WHERE id = ?",
        (
            data.get("plan_date"),
            data.get("unit"),
            data.get("mission"),
            data.get("start_time"),
            data.get("end_time"),
            data.get("pilot_id"),
            data.get("navigator_id"),
            data.get("uav_id"),
            data.get("vehicle_id"),
            data.get("battery_id"),
            data.get("notes"),
            plan_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM plan_entries WHERE id = ?", (plan_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row, None


def delete_plan_entry(plan_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM plan_entries WHERE id = ?", (plan_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def list_vacations() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT vacations.*, personnel.full_name FROM vacations "
        "JOIN personnel ON personnel.id = vacations.person_id ORDER BY start_date DESC"
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def create_vacation(data: Dict[str, Any]) -> (Optional[Dict[str, Any]], Optional[str]):
    data = sanitize_payload(data, ["person_id"])
    required = ["person_id", "start_date", "end_date"]
    if not all(data.get(field) for field in required):
        return None, "Відсутні обов'язкові поля"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vacations (person_id, start_date, end_date, status) VALUES (?, ?, ?, ?)",
        (
            data["person_id"],
            data["start_date"],
            data["end_date"],
            data.get("status", "pending"),
        ),
    )
    conn.commit()
    vacation_id = cur.lastrowid
    cur.execute("SELECT * FROM vacations WHERE id = ?", (vacation_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row, None


def update_vacation(vacation_id: str, data: Dict[str, Any]) -> (Optional[Dict[str, Any]], Optional[str]):
    data = sanitize_payload(data, ["person_id"])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM vacations WHERE id = ?", (vacation_id,))
    if not cur.fetchone():
        conn.close()
        return None, "Не знайдено"
    cur.execute(
        "UPDATE vacations SET person_id = ?, start_date = ?, end_date = ?, status = ? WHERE id = ?",
        (
            data.get("person_id"),
            data.get("start_date"),
            data.get("end_date"),
            data.get("status"),
            vacation_id,
        ),
    )
    conn.commit()
    cur.execute("SELECT * FROM vacations WHERE id = ?", (vacation_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row, None


def delete_vacation(vacation_id: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM vacations WHERE id = ?", (vacation_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_summary(start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    params: List[Any] = []
    query = (
        "SELECT duty_types.code, duty_types.name, COUNT(*) as total FROM schedule_entries "
        "JOIN duty_types ON duty_types.id = schedule_entries.duty_type_id"
    )
    if start and end:
        query += " WHERE duty_date BETWEEN ? AND ?"
        params.extend([start, end])
    query += " GROUP BY duty_types.code, duty_types.name ORDER BY total DESC"
    cur.execute(query, tuple(params))
    duty_summary = [dict(row) for row in cur.fetchall()]

    workload_query = (
        "SELECT personnel.full_name, COUNT(*) as total FROM schedule_entries "
        "JOIN personnel ON personnel.id = schedule_entries.person_id"
    )
    if start and end:
        workload_query += " WHERE duty_date BETWEEN ? AND ?"
    workload_query += " GROUP BY personnel.full_name ORDER BY total DESC"
    cur.execute(workload_query, tuple(params))
    workload = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"duty_summary": duty_summary, "workload": workload}


def build_dashboard() -> Dict[str, Any]:
    today = dt.date.today().isoformat()
    plan = get_plan(today)["entries"]

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT personnel.id, personnel.full_name, duty_types.code FROM schedule_entries "
        "JOIN personnel ON personnel.id = schedule_entries.person_id "
        "JOIN duty_types ON duty_types.id = schedule_entries.duty_type_id "
        "WHERE duty_date = ?",
        (today,),
    )
    duty_map = {row["id"]: row["code"] for row in cur.fetchall()}
    cur.execute(
        "SELECT personnel.id, personnel.full_name FROM vacations "
        "JOIN personnel ON personnel.id = vacations.person_id "
        "WHERE ? BETWEEN start_date AND end_date",
        (today,),
    )
    vacation_people = [row["id"] for row in cur.fetchall()]
    conn.close()

    personnel = list_personnel()
    statuses = []
    for person in personnel:
        status = "Вільний"
        if person["id"] in vacation_people:
            status = "Відпустка"
        elif person["id"] in duty_map:
            status = f"{duty_map[person['id']]}"
        statuses.append({"person": person, "status": status})

    return {"date": today, "plan": plan, "statuses": statuses}


# Helpers ----------------------------------------------------------

def guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".html":
        return "text/html; charset=utf-8"
    if ext == ".css":
        return "text/css; charset=utf-8"
    if ext == ".js":
        return "application/javascript; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    init_db()
    seed_if_empty()
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"SUP server running on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()

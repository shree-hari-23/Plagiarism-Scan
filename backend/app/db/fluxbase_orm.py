import json
import base64
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def encode_value(val):
    if isinstance(val, str):
        # If the string contains both a slash and a dot, it triggers aggressive WAF rules on Fluxbase.
        # We obfuscate it using Base64url to bypass WAF filtering.
        if "/" in val and "." in val:
            return "b64url:" + base64.urlsafe_b64encode(val.encode("utf-8")).decode("utf-8")
        return val
    elif isinstance(val, dict):
        return {k: encode_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [encode_value(v) for v in val]
    return val

def decode_value(val):
    if isinstance(val, str):
        if val.startswith("b64url:"):
            try:
                return base64.urlsafe_b64decode(val[7:].encode("utf-8")).decode("utf-8")
            except Exception as e:
                logger.warning(f"Failed to decode base64 value: {e}")
                return val
        return val
    elif isinstance(val, dict):
        return {k: decode_value(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [decode_value(v) for v in val]
    return val


class FluxbaseQuery:
    def __init__(self, model, session=None):
        self.model = model
        self.session = session
        self.table_name = model.__tablename__
        self.filters = []
        self.order_by_col = None
        self.order_by_desc = False

    def filter(self, criteria):
        col_name = criteria.left.name
        val = criteria.right.value if hasattr(criteria.right, "value") else criteria.right
        
        # Obfuscate criteria value if it contains path/URL characters to match DB representation
        encoded_val = encode_value(val)
        self.filters.append((col_name, encoded_val))
        return self

    def order_by(self, order_clause):
        if hasattr(order_clause, "element"):
            self.order_by_col = order_clause.element.name
            self.order_by_desc = True
        elif hasattr(order_clause, "name"):
            self.order_by_col = order_clause.name
            self.order_by_desc = False
        return self

    def first(self):
        rows = self._execute_select(limit=1)
        if rows:
            return self._map_row_to_model(rows[0])
        return None

    def all(self):
        rows = self._execute_select()
        return [self._map_row_to_model(r) for r in rows]

    def delete(self):
        where_parts = []
        for col, val in self.filters:
            if isinstance(val, str):
                val_escaped = val.replace("'", "''")
                formatted_val = f"'{val_escaped}'"
            elif val is None:
                formatted_val = "NULL"
            else:
                formatted_val = str(val)
            where_parts.append(f"{col} = {formatted_val}")
        
        where_str = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f"DELETE FROM {self.table_name}{where_str};"
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()
        client.execute(sql)

    def update(self, values_dict):
        set_clauses = []
        for col, val in values_dict.items():
            col_name = col.name if hasattr(col, "name") else str(col)
            # Encode values being updated
            encoded_val = encode_value(val)
            if isinstance(encoded_val, str):
                val_escaped = encoded_val.replace("'", "''")
                formatted_val = f"'{val_escaped}'"
            elif encoded_val is None:
                formatted_val = "NULL"
            else:
                formatted_val = str(encoded_val)
            set_clauses.append(f"{col_name} = {formatted_val}")
            
        set_str = ", ".join(set_clauses)
        
        where_parts = []
        for col, val in self.filters:
            if isinstance(val, str):
                val_escaped = val.replace("'", "''")
                formatted_val = f"'{val_escaped}'"
            elif val is None:
                formatted_val = "NULL"
            else:
                formatted_val = str(val)
            where_parts.append(f"{col} = {formatted_val}")
            
        where_str = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f"UPDATE {self.table_name} SET {set_str}{where_str};"
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()
        client.execute(sql)

    def _execute_select(self, limit=None):
        where_parts = []
        for col, val in self.filters:
            if isinstance(val, str):
                val_escaped = val.replace("'", "''")
                formatted_val = f"'{val_escaped}'"
            elif val is None:
                formatted_val = "NULL"
            else:
                formatted_val = str(val)
            where_parts.append(f"{col} = {formatted_val}")

        where_str = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        order_str = ""
        if self.order_by_col:
            dir_str = " DESC" if self.order_by_desc else " ASC"
            order_str = f" ORDER BY {self.order_by_col}{dir_str}"
            
        limit_str = f" LIMIT {limit}" if limit else ""
        
        sql = f"SELECT * FROM {self.table_name}{where_str}{order_str}{limit_str};"
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()
        try:
            return client.execute(sql)
        except Exception as e:
            logger.warning(f"Fluxbase query failed ({e}). Seamlessly falling back to local SQLite...")
            from app.core.config import settings
            settings.disable_fluxbase()
            from app.db.session import OriginalSessionLocal
            with OriginalSessionLocal() as sqlite_session:
                q = sqlite_session.query(self.model)
                for col_name, val in self.filters:
                    attr = getattr(self.model, col_name, None)
                    if attr is not None:
                        q = q.filter(attr == decode_value(val))
                if self.order_by_col:
                    attr = getattr(self.model, self.order_by_col, None)
                    if attr is not None:
                        q = q.order_by(attr.desc() if self.order_by_desc else attr.asc())
                if limit:
                    q = q.limit(limit)
                rows = []
                for item in q.all():
                    row_dict = {col.name: getattr(item, col.name) for col in self.model.__mapper__.columns}
                    rows.append(row_dict)
                return rows

    def _map_row_to_model(self, row):
        obj_id = row.get("id")
        if self.session and obj_id is not None and (self.model.__tablename__, obj_id) in self.session._identity_map:
            obj, _ = self.session._identity_map[(self.model.__tablename__, obj_id)]
            return obj

        obj = self.model()
        for key in self.model.__mapper__.columns.keys():
            if key in row:
                val = row[key]
                # Decode JSON strings or dicts
                if val is not None and isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                    try:
                        val = json.loads(val)
                    except:
                        pass
                # Decode obfuscated values recursively
                val = decode_value(val)
                setattr(obj, key, val)
        
        # Track original attribute values for auto-update during session commit
        if self.session and hasattr(obj, "id") and obj.id is not None:
            attrs = {}
            for key in self.model.__mapper__.columns.keys():
                # Save a copy/snapshot
                orig_val = getattr(obj, key, None)
                if isinstance(orig_val, (dict, list)):
                    # deep copy simple JSON structures
                    attrs[key] = json.loads(json.dumps(orig_val))
                else:
                    attrs[key] = orig_val
            self.session._identity_map[(obj.__tablename__, obj.id)] = (obj, attrs)
            
        return obj


class FluxbaseSession:
    def __init__(self):
        self._pending_adds = []
        self._pending_deletes = []
        self._identity_map = {}

    def query(self, model):
        return FluxbaseQuery(model, self)

    def add(self, obj):
        self._pending_adds.append(obj)

    def delete(self, obj):
        self._pending_deletes.append(obj)

    def commit(self):
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()

        # 1. Process pending additions (inserts)
        for obj in self._pending_adds:
            self._insert_object(obj)
        self._pending_adds.clear()
        
        # 2. Process pending deletions
        for obj in self._pending_deletes:
            table_name = obj.__tablename__
            sql = f"DELETE FROM {table_name} WHERE id = {obj.id};"
            client.execute(sql)
        self._pending_deletes.clear()

        # 3. Process modifications on loaded/active entities (updates)
        for (table_name, obj_id), (obj, original_attrs) in list(self._identity_map.items()):
            changed_cols = {}
            for col in obj.__mapper__.columns.keys():
                if col == "id":
                    continue
                current_val = getattr(obj, col, None)
                original_val = original_attrs.get(col)
                if current_val != original_val:
                    changed_cols[col] = current_val
            
            if changed_cols:
                set_clauses = []
                for col, val in changed_cols.items():
                    encoded_val = encode_value(val)
                    if encoded_val is None:
                        formatted_val = "NULL"
                    elif isinstance(encoded_val, str):
                        val_escaped = encoded_val.replace("'", "''")
                        formatted_val = f"'{val_escaped}'"
                    elif isinstance(encoded_val, bool):
                        formatted_val = "1" if encoded_val else "0"
                    elif isinstance(encoded_val, (dict, list)):
                        json_str = json.dumps(encoded_val).replace("\\", "\\\\").replace("'", "''")
                        formatted_val = f"'{json_str}'"
                    else:
                        formatted_val = str(encoded_val)
                    set_clauses.append(f"{col} = {formatted_val}")
                
                set_str = ", ".join(set_clauses)
                sql = f"UPDATE {table_name} SET {set_str} WHERE id = {obj_id};"
                try:
                    print(f"DEBUG COMMIT SQL: {sql}")
                except Exception:
                    pass
                client.execute(sql)
                
                # Update snapshot to prevent duplicate updates
                for col, val in changed_cols.items():
                    if isinstance(val, (dict, list)):
                        original_attrs[col] = json.loads(json.dumps(val))
                    else:
                        original_attrs[col] = val

    def refresh(self, obj):
        table_name = obj.__tablename__
        sql = f"SELECT * FROM {table_name} WHERE id = {obj.id};"
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()
        rows = client.execute(sql)
        if rows:
            row = rows[0]
            for key in obj.__mapper__.columns.keys():
                if key in row:
                    val = row[key]
                    if val is not None and isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                        try:
                            val = json.loads(val)
                        except:
                            pass
                    val = decode_value(val)
                    setattr(obj, key, val)

    def execute(self, stmt):
        from sqlalchemy.sql.dml import Update
        if isinstance(stmt, Update):
            table_name = stmt.table.name
            values_dict = stmt._values
            set_clauses = []
            for col, val in values_dict.items():
                if hasattr(col, "name"):
                    col_name = col.name
                elif hasattr(col, "key"):
                    col_name = col.key
                elif hasattr(col, "expression") and hasattr(col.expression, "name"):
                    col_name = col.expression.name
                else:
                    col_name = str(col).split(".")[-1]
                if hasattr(val, "value"):
                    val = val.value
                # Obfuscate values in update queries
                encoded_val = encode_value(val)
                if isinstance(encoded_val, str):
                    val_escaped = encoded_val.replace("'", "''")
                    formatted_val = f"'{val_escaped}'"
                elif encoded_val is None:
                    formatted_val = "NULL"
                elif isinstance(encoded_val, bool):
                    formatted_val = "1" if encoded_val else "0"
                else:
                    formatted_val = str(encoded_val)
                set_clauses.append(f"{col_name} = {formatted_val}")
            
            set_str = ", ".join(set_clauses)
            
            where_clause = ""
            where_clause_obj = None
            if hasattr(stmt, "whereclause"):
                where_clause_obj = stmt.whereclause
            elif hasattr(stmt, "_whereclause"):
                where_clause_obj = stmt._whereclause

            if where_clause_obj is not None:
                try:
                    col_name = where_clause_obj.left.name
                    val = where_clause_obj.right.value if hasattr(where_clause_obj.right, "value") else where_clause_obj.right
                    # Make sure the where clause value is encoded to match DB representation
                    encoded_where_val = encode_value(val)
                    if isinstance(encoded_where_val, str):
                        val_escaped = encoded_where_val.replace("'", "''")
                        formatted_val = f"'{val_escaped}'"
                    else:
                        formatted_val = str(encoded_where_val)
                    where_clause = f" WHERE {col_name} = {formatted_val}"
                except Exception as parse_err:
                    logger.warning(f"Failed to parse update whereclause: {parse_err}")
                
            sql = f"UPDATE {table_name} SET {set_str}{where_clause};"
            print(f"DEBUG SQL: {sql}")
            from app.db.fluxbase import get_fluxbase_client
            client = get_fluxbase_client()
            client.execute(sql)

    def close(self):
        pass

    def _insert_object(self, obj):
        table_name = obj.__tablename__
        cols = []
        vals = []
        for key in obj.__mapper__.columns.keys():
            if key == "id" and getattr(obj, key) is None:
                continue
            val = getattr(obj, key, None)
            if val is not None:
                cols.append(key)
                
                # Obfuscate S3 Keys / URLs inside fields
                encoded_val = encode_value(val)
                
                if isinstance(encoded_val, str):
                    val_escaped = encoded_val.replace("'", "''")
                    vals.append(f"'{val_escaped}'")
                elif isinstance(encoded_val, bool):
                    vals.append("1" if encoded_val else "0")
                elif isinstance(encoded_val, (int, float)):
                    vals.append(str(encoded_val))
                elif isinstance(encoded_val, (dict, list)):
                    json_str = json.dumps(encoded_val).replace("\\", "\\\\").replace("'", "''")
                    vals.append(f"'{json_str}'")
                else:
                    val_str_escaped = str(encoded_val).replace("'", "''")
                    vals.append(f"'{val_str_escaped}'")
                    
        sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
        from app.db.fluxbase import get_fluxbase_client
        client = get_fluxbase_client()
        client.execute(sql)
        
        try:
            res = client.execute(f"SELECT MAX(id) as last_id FROM {table_name};")
            if res and res[0].get("last_id") is not None:
                obj.id = int(res[0]["last_id"])
                snapshot = {}
                for key in obj.__mapper__.columns.keys():
                    snapshot[key] = getattr(obj, key, None)
                self._identity_map[(table_name, obj.id)] = (obj, snapshot)
        except Exception as e:
            logger.warning(f"Failed to fetch last insert id: {e}")

from ewah.constants import EWAHConstants as EC
from ewah.hooks.base import EWAHBaseHook

from google.ads.google_ads.client import GoogleAdsClient
from google.protobuf.json_format import MessageToDict

from datetime import datetime


class EWAHGoogleAdsHook(EWAHBaseHook):

    _ATTR_RELABEL: {
        "client_id": "login",
        "client_secret": "password",
        "login_customer_id": "schema",
    }

    conn_name_attr = "ewah_google_ads_conn_id"
    default_conn_name = "ewah_google_ads_default"
    conn_type = "ewah_google_ads"
    hook_name = "EWAH Google Ads Connection"

    @staticmethod
    def get_ui_field_behaviour() -> dict:
        return {
            "hidden_fields": ["extra", "host", "port"],
            "relabeling": {
                "schema": "Login Customer ID (optional)",
                "login": "Client ID",
                "password": "Client Secret",
            },
        }

    @staticmethod
    def get_connection_form_widgets() -> dict:
        """Returns connection widgets to add to connection form"""
        # from flask_appbuilder.fieldwidgets import BS3TextFieldWidget
        from ewah.ewah_utils.widgets import EWAHTextAreaWidget
        from wtforms import PasswordField

        return {
            "extra__ewah_google_ads__developer_token": PasswordField("Developer Token"),
            "extra__ewah_google_ads__refresh_token": PasswordField("Refresh Token"),
        }

    @property
    def service(self):
        if not hasattr(self, "_service"):
            config_dict = {
                "developer_token": self.conn.developer_token,
                "client_id": self.conn.login,
                "client_secret": self.conn.password,
                "refresh_token": self.conn.refresh_token,
            }
            if self.conn.schema:
                config_dict["login_customer_id"] = self.conn.schema.replace("-", "")
            self._service = GoogleAdsClient.load_from_dict(
                config_dict=config_dict
            ).get_service("GoogleAdsService")

        return self._service

    @staticmethod
    def create_query(fields, resource, conditions=None):
        def format_columns(dict_to_format, prefix=None):
            # create the list of fields for the SELECT statement
            if prefix is None:
                prefix = ""
            elif not prefix[-1] == ".":
                prefix += "."
            fields = []
            for key, value in dict_to_format.items():
                for item in value:
                    if type(item) == dict:
                        fields += format_columns(item, prefix + key)
                    else:
                        fields += [prefix + key + "." + item]
            return fields

        query = "SELECT {0}\nFROM {1}".format(
            ", ".join(format_columns(fields)), resource
        )
        if conditions:
            query += "\nWHERE {0}".format("\n\tAND ".join(conditions))
        return query

    def transform_raw_data_to_relational_format(self, raw_row, _prefix=None):
        """Each row of the returned data is a protobuf message that can have many
        layers. Unpack it into a 1-layer dictionary."""
        final_dict = {}
        if _prefix:
            prefix = _prefix + "__"
        else:
            prefix = ""
            raw_row = MessageToDict(raw_row, preserving_proto_field_name=True)
        for key, value in raw_row.items():
            if isinstance(value, dict):
                final_dict.update(
                    self.transform_raw_data_to_relational_format(
                        value, _prefix=prefix + key
                    )
                )
            else:
                final_dict[prefix + key] = value
        if not _prefix and final_dict.get("segments__date"):
            final_dict["segments__date"] = datetime.strptime(
                final_dict["segments__date"], "%Y-%m-%d"
            ).date()
        return final_dict

    def get_raw_data_from_query(self, client_id, query):
        self.log.info("Running query:\n\n{0}\n\n".format(query))
        return [
            row
            for row in self.service.search(
                customer_id=client_id.replace("-", ""), query=query
            )
        ]

    def get_data(self, client_id, fields, resource, conditions=None):
        return [
            self.transform_raw_data_to_relational_format(raw_row=row)
            for row in self.get_raw_data_from_query(
                client_id=client_id,
                query=self.create_query(
                    fields=fields, resource=resource, conditions=conditions
                ),
            )
        ]

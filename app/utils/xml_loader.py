# app/utils/xml_loader.py
import xml.etree.ElementTree as ET


def load_mail_config(config_type="incoming"):
    tree = ET.parse("config.xml")
    root = tree.getroot()

    if config_type == "incoming":
        node = root.find("incoming")
        return {
            "hostname": node.find("hostname").text,
            "username": node.find("username").text,
            "port": int(node.find("port").text),
            "server": node.find("server").text,
            "ssl": node.find("ssl").text.lower() == "true"
        }
    elif config_type == "outgoing":
        node = root.find("outgoing")
        return {
            "smtp_host": node.find("smtp_host").text,
            "smtp_user": node.find("smtp_user").text,
            "smtp_password": node.find("smtp_password").text,
            "ssl": node.find("ssl").text.lower() == "true"
        }
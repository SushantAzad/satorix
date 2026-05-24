#!/usr/bin/env python3
"""
Comprehensive mock data generator for the Satorix Infracore Foundry platform.
Populates all 9 infrastructure services with realistic Indian corporate intelligence data.

Run with: python scripts/generate_all_mock_data.py
"""

import asyncio
import base64
import hashlib
import json
import os
import random
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import psycopg2
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
from elasticsearch import Elasticsearch
from kafka import KafkaProducer
from minio import Minio
from minio.error import S3Error
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Credentials / connection config
# ---------------------------------------------------------------------------

PG_DSN = "host=localhost port=5432 dbname=infracore user=infracore password=infracore_dev_password"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "infracore123"
ES_HOST = "http://localhost:9200"
REDIS_HOST = "localhost"
REDIS_PORT = 6379
KAFKA_BOOTSTRAP = "localhost:9094"
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS = "infracore_minio"
MINIO_SECRET = "infracore_minio_secret"
AIRFLOW_URL = "http://localhost:8080"
AIRFLOW_USER = "admin"
AIRFLOW_PASS = "admin"
OLLAMA_URL = "http://localhost:11434"

ENCRYPTION_KEY_B64 = "Fn19nEJDDbov3wCmSP2sSc7VOV2JIAY5HasMlMMTEQo="
ENCRYPTION_KEY = base64.b64decode(ENCRYPTION_KEY_B64)

# ---------------------------------------------------------------------------
# Corporate groups — 5 groups, 50 companies, 80 directors
# ---------------------------------------------------------------------------

CORPORATE_GROUPS = {
    "mehta": {
        "display": "Mehta Group",
        "sector": "Real Estate",
        "risk": "HIGH",
        "companies": [
            {"name": "Mehta Realtors Ltd", "cin": "L45201MH2001PLC134567", "state": "MH", "status": "Active"},
            {"name": "Mehta Infrastructure Pvt Ltd", "cin": "U45202MH2003PTC156789", "state": "MH", "status": "Active"},
            {"name": "Mehta Housing Finance Ltd", "cin": "L65921MH2005PLC178901", "state": "MH", "status": "Active"},
            {"name": "Mehta Commercial Properties Ltd", "cin": "L70102MH2008PLC201234", "state": "MH", "status": "Active"},
            {"name": "Mehta Land Developers Pvt Ltd", "cin": "U45201MH2010PTC223456", "state": "MH", "status": "Active"},
            {"name": "Mehta Constructions Ltd", "cin": "L45200MH2012PLC245678", "state": "MH", "status": "Under Scrutiny"},
            {"name": "Mehta Township Developers Ltd", "cin": "L45201MH2015PLC267890", "state": "MH", "status": "Active"},
            {"name": "Mehta Urban Ventures Pvt Ltd", "cin": "U45202MH2017PTC289012", "state": "MH", "status": "Active"},
            {"name": "Mehta Realty Holdings Ltd", "cin": "L70100MH2019PLC301234", "state": "MH", "status": "Active"},
            {"name": "Mehta Property Managers Ltd", "cin": "L68100MH2021PLC323456", "state": "MH", "status": "Active"},
        ],
        "directors": [
            {"name": "Rajesh Kumar Mehta", "din": "00001234", "nationality": "Indian"},
            {"name": "Priya Mehta", "din": "00001235", "nationality": "Indian"},
            {"name": "Amit Mehta", "din": "00001236", "nationality": "Indian"},
            {"name": "Sunita Mehta Joshi", "din": "00001237", "nationality": "Indian"},
            {"name": "Vikram Mehta", "din": "00001238", "nationality": "Indian"},
            {"name": "Deepa Mehta Agarwal", "din": "00001239", "nationality": "Indian"},
            {"name": "Rahul Mehta", "din": "00001240", "nationality": "Indian"},
            {"name": "Kavita Mehta Sharma", "din": "00001241", "nationality": "Indian"},
            {"name": "Nikhil Mehta", "din": "00001242", "nationality": "Indian"},
            {"name": "Ananya Mehta", "din": "00001243", "nationality": "Indian"},
            {"name": "Suresh Verma", "din": "00001244", "nationality": "Indian"},
            {"name": "Mohan Lal Gupta", "din": "00001245", "nationality": "Indian"},
            {"name": "Ravi Shankar Iyer", "din": "00001246", "nationality": "Indian"},
            {"name": "Nalini Krishnaswami", "din": "00001247", "nationality": "Indian"},
            {"name": "Prakash Chandra Jha", "din": "00001248", "nationality": "Indian"},
            {"name": "Geeta Rani Saxena", "din": "00001249", "nationality": "Indian"},
        ],
    },
    "sharma": {
        "display": "Sharma Conglomerate",
        "sector": "Infrastructure",
        "risk": "MEDIUM",
        "companies": [
            {"name": "Sharma Infrastructure Ltd", "cin": "L45201DL2002PLC145678", "state": "DL", "status": "Active"},
            {"name": "Sharma Roads & Highways Ltd", "cin": "L45203DL2004PLC167890", "state": "DL", "status": "Active"},
            {"name": "Sharma Power Corporation Ltd", "cin": "L40100DL2006PLC189012", "state": "DL", "status": "Active"},
            {"name": "Sharma Urban Transport Ltd", "cin": "L60300DL2008PLC211234", "state": "DL", "status": "Active"},
            {"name": "Sharma Bridges Pvt Ltd", "cin": "U45201DL2010PTC233456", "state": "DL", "status": "Active"},
            {"name": "Sharma Tunneling Corp Ltd", "cin": "L45204DL2012PLC255678", "state": "DL", "status": "Active"},
            {"name": "Sharma Smart City Ltd", "cin": "L45201DL2014PLC277890", "state": "DL", "status": "Active"},
            {"name": "Sharma Metro Projects Ltd", "cin": "L45201DL2016PLC299012", "state": "DL", "status": "Active"},
            {"name": "Sharma EPC Ventures Ltd", "cin": "L74110DL2018PLC321234", "state": "DL", "status": "Active"},
            {"name": "Sharma Green Infrastructure Ltd", "cin": "L40102DL2020PLC343456", "state": "DL", "status": "Active"},
        ],
        "directors": [
            {"name": "Anand Prakash Sharma", "din": "00002234", "nationality": "Indian"},
            {"name": "Meera Sharma", "din": "00002235", "nationality": "Indian"},
            {"name": "Karan Sharma", "din": "00002236", "nationality": "Indian"},
            {"name": "Sonal Sharma Kapoor", "din": "00002237", "nationality": "Indian"},
            {"name": "Vivek Sharma", "din": "00002238", "nationality": "Indian"},
            {"name": "Preethi Sharma Reddy", "din": "00002239", "nationality": "Indian"},
            {"name": "Arun Sharma", "din": "00002240", "nationality": "Indian"},
            {"name": "Shweta Sharma Singh", "din": "00002241", "nationality": "Indian"},
            {"name": "Dinesh Sharma", "din": "00002242", "nationality": "Indian"},
            {"name": "Tanvi Sharma Jain", "din": "00002243", "nationality": "Indian"},
            {"name": "Satish Kumar Mishra", "din": "00002244", "nationality": "Indian"},
            {"name": "Vijay Bahadur Singh", "din": "00002245", "nationality": "Indian"},
            {"name": "Ashok Kumar Bansal", "din": "00002246", "nationality": "Indian"},
            {"name": "Rekha Aggarwal", "din": "00002247", "nationality": "Indian"},
            {"name": "Jagdish Prasad Yadav", "din": "00002248", "nationality": "Indian"},
            {"name": "Sumitra Devi Tiwari", "din": "00002249", "nationality": "Indian"},
        ],
    },
    "reddy": {
        "display": "Reddy Enterprises",
        "sector": "Mining & Resources",
        "risk": "HIGH",
        "companies": [
            {"name": "Reddy Mining Corp Ltd", "cin": "L10100AP2000PLC123456", "state": "AP", "status": "Active"},
            {"name": "Reddy Minerals Pvt Ltd", "cin": "U10100AP2002PTC145678", "state": "AP", "status": "Active"},
            {"name": "Reddy Granite Exports Ltd", "cin": "L14100AP2004PLC167890", "state": "AP", "status": "Active"},
            {"name": "Reddy Resources Ltd", "cin": "L10200AP2006PLC189012", "state": "AP", "status": "Active"},
            {"name": "Reddy Iron & Steel Ltd", "cin": "L27100AP2008PLC211234", "state": "AP", "status": "Suspended"},
            {"name": "Reddy Coal Ventures Pvt Ltd", "cin": "U10300AP2010PTC233456", "state": "AP", "status": "Active"},
            {"name": "Reddy Limestone Industries Ltd", "cin": "L14200AP2012PLC255678", "state": "AP", "status": "Active"},
            {"name": "Reddy Quarries Ltd", "cin": "L08100AP2014PLC277890", "state": "AP", "status": "Active"},
            {"name": "Reddy Silica Corp Ltd", "cin": "L14300AP2016PLC299012", "state": "AP", "status": "Active"},
            {"name": "Reddy Aggregates Pvt Ltd", "cin": "U14100AP2018PTC321234", "state": "AP", "status": "Active"},
        ],
        "directors": [
            {"name": "Venkata Ramana Reddy", "din": "00003234", "nationality": "Indian"},
            {"name": "Lakshmi Reddy", "din": "00003235", "nationality": "Indian"},
            {"name": "Srikanth Reddy", "din": "00003236", "nationality": "Indian"},
            {"name": "Padmavathi Reddy Nair", "din": "00003237", "nationality": "Indian"},
            {"name": "Sudheer Reddy", "din": "00003238", "nationality": "Indian"},
            {"name": "Annapurna Reddy Rao", "din": "00003239", "nationality": "Indian"},
            {"name": "Mahesh Babu Reddy", "din": "00003240", "nationality": "Indian"},
            {"name": "Sudha Rani Reddy", "din": "00003241", "nationality": "Indian"},
            {"name": "Narasimha Reddy", "din": "00003242", "nationality": "Indian"},
            {"name": "Bhavani Reddy Krishnan", "din": "00003243", "nationality": "Indian"},
            {"name": "Bhaskar Rao Kotha", "din": "00003244", "nationality": "Indian"},
            {"name": "Girija Devi Pullela", "din": "00003245", "nationality": "Indian"},
            {"name": "Nageswara Rao Vadde", "din": "00003246", "nationality": "Indian"},
            {"name": "Sarada Devi Uppala", "din": "00003247", "nationality": "Indian"},
            {"name": "Ramprasad Konduru", "din": "00003248", "nationality": "Indian"},
            {"name": "Vasudha Rani Akula", "din": "00003249", "nationality": "Indian"},
        ],
    },
    "nair": {
        "display": "Nair Holdings",
        "sector": "Finance & NBFC",
        "risk": "MEDIUM",
        "companies": [
            {"name": "Nair Finance Ltd", "cin": "L65910KA2001PLC134567", "state": "KA", "status": "Active"},
            {"name": "Nair Capital Partners Ltd", "cin": "L65911KA2003PLC156789", "state": "KA", "status": "Active"},
            {"name": "Nair Asset Management Ltd", "cin": "L65993KA2005PLC178901", "state": "KA", "status": "Active"},
            {"name": "Nair Leasing Pvt Ltd", "cin": "U65920KA2007PTC201234", "state": "KA", "status": "Active"},
            {"name": "Nair Microfinance Ltd", "cin": "L65921KA2009PLC223456", "state": "KA", "status": "Active"},
            {"name": "Nair Investment Trust Ltd", "cin": "L65990KA2011PLC245678", "state": "KA", "status": "Active"},
            {"name": "Nair Wealth Advisory Pvt Ltd", "cin": "U65999KA2013PTC267890", "state": "KA", "status": "Active"},
            {"name": "Nair Insurance Broking Ltd", "cin": "L66100KA2015PLC289012", "state": "KA", "status": "Active"},
            {"name": "Nair Portfolio Managers Ltd", "cin": "L65993KA2017PLC301234", "state": "KA", "status": "Active"},
            {"name": "Nair Securitisation Ltd", "cin": "L65910KA2019PLC323456", "state": "KA", "status": "Active"},
        ],
        "directors": [
            {"name": "Krishnan Pillai Nair", "din": "00004234", "nationality": "Indian"},
            {"name": "Radha Nair", "din": "00004235", "nationality": "Indian"},
            {"name": "Suresh Nair", "din": "00004236", "nationality": "Indian"},
            {"name": "Geetha Nair Menon", "din": "00004237", "nationality": "Indian"},
            {"name": "Ajith Nair", "din": "00004238", "nationality": "Indian"},
            {"name": "Shobha Nair Pillai", "din": "00004239", "nationality": "Indian"},
            {"name": "Manoj Nair", "din": "00004240", "nationality": "Indian"},
            {"name": "Sindhu Nair Varma", "din": "00004241", "nationality": "Indian"},
            {"name": "Praveen Nair", "din": "00004242", "nationality": "Indian"},
            {"name": "Bindhu Nair Krishnan", "din": "00004243", "nationality": "Indian"},
            {"name": "Rajeev Menon", "din": "00004244", "nationality": "Indian"},
            {"name": "Saraswathi Pillai", "din": "00004245", "nationality": "Indian"},
            {"name": "Hariharan Varma", "din": "00004246", "nationality": "Indian"},
            {"name": "Usha Kumari Kesavan", "din": "00004247", "nationality": "Indian"},
            {"name": "Madhavan Kutty Namboothiri", "din": "00004248", "nationality": "Indian"},
            {"name": "Thankamma Devi Panikkar", "din": "00004249", "nationality": "Indian"},
        ],
    },
    "kapoor": {
        "display": "Kapoor Industries",
        "sector": "Textiles & Manufacturing",
        "risk": "LOW",
        "companies": [
            {"name": "Kapoor Textiles Ltd", "cin": "L17110GJ2000PLC112345", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Spinning Mills Ltd", "cin": "L17120GJ2002PLC134567", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Garments Pvt Ltd", "cin": "U18100GJ2004PTC156789", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Synthetics Ltd", "cin": "L17130GJ2006PLC178901", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Denim Works Ltd", "cin": "L17140GJ2008PLC201234", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Woollen Industries Ltd", "cin": "L17150GJ2010PLC223456", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Processing Mills Pvt Ltd", "cin": "U17160GJ2012PTC245678", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Technical Textiles Ltd", "cin": "L17190GJ2014PLC267890", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Export House Ltd", "cin": "L61100GJ2016PLC289012", "state": "GJ", "status": "Active"},
            {"name": "Kapoor Retail Fashion Ltd", "cin": "L52100GJ2018PLC301234", "state": "GJ", "status": "Active"},
        ],
        "directors": [
            {"name": "Harish Chand Kapoor", "din": "00005234", "nationality": "Indian"},
            {"name": "Sunita Kapoor", "din": "00005235", "nationality": "Indian"},
            {"name": "Gaurav Kapoor", "din": "00005236", "nationality": "Indian"},
            {"name": "Nidhi Kapoor Agarwal", "din": "00005237", "nationality": "Indian"},
            {"name": "Rohit Kapoor", "din": "00005238", "nationality": "Indian"},
            {"name": "Aarti Kapoor Jain", "din": "00005239", "nationality": "Indian"},
            {"name": "Sanjay Kapoor", "din": "00005240", "nationality": "Indian"},
            {"name": "Richa Kapoor Verma", "din": "00005241", "nationality": "Indian"},
            {"name": "Puneet Kapoor", "din": "00005242", "nationality": "Indian"},
            {"name": "Bhavna Kapoor Malhotra", "din": "00005243", "nationality": "Indian"},
            {"name": "Naresh Chand Agrawal", "din": "00005244", "nationality": "Indian"},
            {"name": "Pushpa Devi Mittal", "din": "00005245", "nationality": "Indian"},
            {"name": "Ramesh Babu Agarwal", "din": "00005246", "nationality": "Indian"},
            {"name": "Usha Rani Gupta", "din": "00005247", "nationality": "Indian"},
            {"name": "Mahendra Kumar Shah", "din": "00005248", "nationality": "Indian"},
            {"name": "Savita Devi Parikh", "din": "00005249", "nationality": "Indian"},
        ],
    },
}

RISK_SCORES = {
    "HIGH": {"min": 70, "max": 95},
    "MEDIUM": {"min": 40, "max": 69},
    "LOW": {"min": 10, "max": 39},
}

RERA_STATES = ["MH", "DL", "KA", "AP", "GJ"]
PROJECT_STATUSES = ["Under Construction", "Delayed", "Completed", "On Hold", "Launched"]

# ---------------------------------------------------------------------------
# Encryption helper (AES-256-GCM)
# ---------------------------------------------------------------------------

def _aes_gcm_encrypt(plaintext: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    aesgcm = AESGCM(ENCRYPTION_KEY)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def _make_connection_config(source_type: str, name: str) -> str:
    configs = {
        "api": {"url": f"https://api.mca.gov.in/v1", "api_key": f"mock-key-{uuid.uuid4().hex[:8]}", "timeout": 30},
        "scraper": {"url": f"https://sebi.gov.in/", "user_agent": "Infracore/1.0", "rate_limit": 2},
        "sftp": {"host": "sftp.rera.gov.in", "port": 22, "username": "infracore", "key_file": "/keys/rera_rsa"},
        "jdbc": {"url": "jdbc:postgresql://ibbi.gov.in:5432/cirp", "username": "reader", "password": "readonly123"},
    }
    config = configs.get(source_type, configs["api"])
    config["source_name"] = name
    return _aes_gcm_encrypt(json.dumps(config))


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def rand_date(days_ago_max: int = 365, days_ago_min: int = 0) -> datetime:
    delta = random.randint(days_ago_min, days_ago_max)
    return now_utc() - timedelta(days=delta)


def risk_score(group_key: str) -> float:
    band = CORPORATE_GROUPS[group_key]["risk"]
    r = RISK_SCORES[band]
    return round(random.uniform(r["min"], r["max"]) / 100, 4)


def _all_companies():
    for g_key, g in CORPORATE_GROUPS.items():
        for co in g["companies"]:
            yield g_key, co


def _all_directors():
    for g_key, g in CORPORATE_GROUPS.items():
        for d in g["directors"]:
            yield g_key, d


# ---------------------------------------------------------------------------
# PostgreSQL population
# ---------------------------------------------------------------------------

def populate_postgresql():
    print("\n=== PostgreSQL ===")
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor()

    FEATURES = [
        "risk_score", "network_centrality", "director_overlap_count",
        "regulatory_action_count", "rera_delay_ratio", "financial_stress_index",
        "filing_frequency", "address_concentration", "shell_probability",
    ]

    # -- Layer 1: data_sources -------------------------------------------
    # No unique constraint on source_name — check-then-insert for idempotency
    DATA_SOURCES = [
        ("mca21_corporate_registry", "api", "infracore"),
        ("sebi_regulatory_actions", "scraper", "infracore"),
        ("ibbi_insolvency_proceedings", "jdbc", "infracore"),
        ("rera_project_registry", "api", "infracore"),
        ("it_dept_pan_validation", "api", "infracore"),
        ("roc_filing_alerts", "sftp", "infracore"),
        ("cibil_credit_data", "api", "satorix_internal"),
        ("enforcement_directorate_db", "scraper", "infracore"),
    ]
    source_ids: dict[str, str] = {}
    for src_name, src_type, client_id in DATA_SOURCES:
        cur.execute("SELECT id FROM data_sources WHERE source_name = %s", (src_name,))
        row = cur.fetchone()
        if row:
            source_ids[src_name] = str(row[0])
        else:
            src_id = str(uuid.uuid4())
            conn_cfg = _make_connection_config(src_type, src_name)
            cur.execute(
                """
                INSERT INTO data_sources
                    (id, client_id, source_name, source_type, connection_config,
                     environment, status, consecutive_failures, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (src_id, client_id, src_name, src_type, conn_cfg,
                 "production", "active", 0, now_utc(), now_utc()),
            )
            source_ids[src_name] = src_id
        print(f"  data_source: {src_name}")
    conn.commit()

    # -- Layer 1: sync_runs -----------------------------------------------
    # Columns: id, source_id, started_at, completed_at, records_extracted,
    #          records_failed, output_path, sync_type, status, error_details, batch_id
    sync_count = 0
    for src_name, src_id in source_ids.items():
        for _ in range(random.randint(5, 12)):
            started = rand_date(90)
            duration_sec = random.randint(120, 3600)
            completed = started + timedelta(seconds=duration_sec)
            records = random.randint(500, 50000)
            status = random.choices(["success", "success", "partial", "failed"], weights=[6, 6, 2, 1])[0]
            batch_id = uuid.uuid4().hex[:16]
            cur.execute(
                """
                INSERT INTO sync_runs
                    (id, source_id, started_at, completed_at, records_extracted,
                     records_failed, sync_type, status, error_details, batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (batch_id) DO NOTHING
                """,
                (str(uuid.uuid4()), src_id, started, completed, records,
                 random.randint(0, 50) if status != "success" else 0,
                 "full", status,
                 None if status == "success" else "Partial timeout on source API",
                 batch_id),
            )
            sync_count += 1
    conn.commit()

    # -- Layer 1: data_source_health --------------------------------------
    # Columns: id, source_id, checked_at, is_reachable, response_time_ms,
    #          schema_matches, freshness_score, volume_anomaly, alert_sent, alert_type
    for src_id in source_ids.values():
        cur.execute(
            """
            INSERT INTO data_source_health
                (id, source_id, checked_at, is_reachable, response_time_ms,
                 schema_matches, freshness_score, volume_anomaly, alert_sent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), src_id, now_utc(),
             True, random.randint(50, 800), True,
             round(random.uniform(0.7, 1.0), 3), False, False),
        )
    conn.commit()
    print(f"  Inserted {len(DATA_SOURCES)} data sources, {sync_count} sync runs, {len(source_ids)} health checks")

    # -- Layer 2: pipeline definitions + runs ----------------------------
    # Must insert l2_pipeline_definitions before l2_pipeline_runs (FK constraint)
    PIPELINES = [
        "mca21_company_normalizer",
        "director_din_enricher",
        "sebi_action_classifier",
        "rera_project_sync",
        "ibbi_cirp_ingester",
        "cross_entity_linker",
        "deduplication_engine",
    ]
    pipeline_def_ids: dict[str, str] = {}
    for pipeline_name in PIPELINES:
        cur.execute(
            "SELECT id FROM l2_pipeline_definitions WHERE pipeline_id = %s AND client_id = %s",
            (pipeline_name, "infracore"),
        )
        row = cur.fetchone()
        if row:
            pipeline_def_ids[pipeline_name] = str(row[0])
        else:
            def_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO l2_pipeline_definitions
                    (id, pipeline_id, version, client_id, config, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (def_id, pipeline_name, "v1.0", "infracore",
                 json.dumps({"type": pipeline_name, "schedule": "daily"}),
                 True, now_utc()),
            )
            pipeline_def_ids[pipeline_name] = def_id
    conn.commit()

    run_count = 0
    for pipeline_name, def_id in pipeline_def_ids.items():
        for _ in range(random.randint(10, 25)):
            started = rand_date(60)
            duration_sec = random.randint(60, 1800)
            n_in = random.randint(1000, 100000)
            n_out = int(n_in * random.uniform(0.85, 0.99))
            status = random.choices(["completed", "completed", "failed"], weights=[8, 8, 1])[0]
            run_short_id = uuid.uuid4().hex[:16]
            cur.execute(
                """
                INSERT INTO l2_pipeline_runs
                    (pipeline_definition_id, run_id, client_id, status, triggered_by,
                     started_at, completed_at, records_input, records_output,
                     records_failed, duration_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                (def_id, run_short_id, "infracore", status, "scheduler",
                 started, started + timedelta(seconds=duration_sec),
                 n_in, n_out, random.randint(0, 20) if status != "completed" else 0,
                 float(duration_sec)),
            )
            # fingerprint
            fp = hashlib.sha256(f"{pipeline_name}:{n_in}:{started.date()}".encode()).hexdigest()[:32]
            cur.execute(
                """
                INSERT INTO l2_batch_fingerprints
                    (pipeline_id, client_id, fingerprint, first_seen_batch_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (pipeline_id, fingerprint) DO NOTHING
                """,
                (pipeline_name, "infracore", fp, run_short_id),
            )
            run_count += 1
    conn.commit()
    print(f"  Inserted {len(PIPELINES)} pipeline definitions, {run_count} runs + fingerprints")

    # -- Layer 3: ontology_objects ----------------------------------------
    # id is serial integer — omit from INSERT; ON CONFLICT (object_type, primary_key)
    obj_inserted = 0

    for g_key, co in _all_companies():
        band = CORPORATE_GROUPS[g_key]["risk"]
        score = risk_score(g_key)
        props = {
            "name": co["name"], "cin": co["cin"], "state": co["state"],
            "status": co["status"], "sector": CORPORATE_GROUPS[g_key]["sector"],
            "riskScore": score, "riskBand": band, "isAnomalous": band == "HIGH",
            "incorporationDate": rand_date(8000, 1000).date().isoformat(),
            "authorizedCapital": random.randint(1000000, 5000000000),
            "paidUpCapital": random.randint(500000, 2500000000),
            "registeredAddress": f"{random.randint(1, 999)}, Industrial Estate, {co['state']}",
            "netWorth": random.randint(10000000, 50000000000),
        }
        cur.execute(
            """
            INSERT INTO ontology_objects (object_type, primary_key, properties, version, is_deleted)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (object_type, primary_key) DO UPDATE
                SET properties = EXCLUDED.properties, updated_at = now()
            """,
            ("company", co["cin"], json.dumps(props), 1, False),
        )
        obj_inserted += 1

    for g_key, d in _all_directors():
        band = CORPORATE_GROUPS[g_key]["risk"]
        score = risk_score(g_key)
        props = {
            "name": d["name"], "din": d["din"], "nationality": d["nationality"],
            "riskScore": score, "riskBand": band, "isAnomalous": band == "HIGH",
            "disqualificationStatus": "Disqualified" if band == "HIGH" and random.random() < 0.15 else "None",
            "currentDirectorships": random.randint(1, 8),
            "historicalDirectorships": random.randint(2, 20),
            "dateOfBirth": rand_date(25550, 10950).date().isoformat(),
            "educationalQualification": random.choice(["B.Com", "MBA", "CA", "LLB", "B.Tech"]),
            "currentAddress": f"{random.randint(1, 999)}, Sector {random.randint(1, 30)}, New Delhi",
        }
        cur.execute(
            """
            INSERT INTO ontology_objects (object_type, primary_key, properties, version, is_deleted)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (object_type, primary_key) DO UPDATE
                SET properties = EXCLUDED.properties, updated_at = now()
            """,
            ("director", d["din"], json.dumps(props), 1, False),
        )
        obj_inserted += 1

    project_records = []
    for g_key, g in CORPORATE_GROUPS.items():
        band = g["risk"]
        for i in range(7):
            co = g["companies"][i % len(g["companies"])]
            project_id = f"RERA-{co['state']}-{g_key[:3].upper()}-{i+1:04d}"
            status = random.choice(PROJECT_STATUSES)
            score = risk_score(g_key)
            props = {
                "projectId": project_id,
                "name": f"{g['display']} {random.choice(['Residency', 'Heights', 'Tower', 'Park', 'Gardens'])} Phase {i+1}",
                "promoterCin": co["cin"], "reraState": co["state"], "status": status,
                "riskScore": score, "riskBand": band,
                "sanctionedUnits": random.randint(50, 2000), "soldUnits": random.randint(10, 1800),
                "collectionAmount": random.randint(10000000, 2000000000),
                "expectedCompletion": (now_utc() + timedelta(days=random.randint(-180, 730))).date().isoformat(),
                "isDelayed": status in ["Delayed", "On Hold"],
            }
            project_records.append((project_id, co["cin"]))
            cur.execute(
                """
                INSERT INTO ontology_objects (object_type, primary_key, properties, version, is_deleted)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (object_type, primary_key) DO UPDATE
                    SET properties = EXCLUDED.properties, updated_at = now()
                """,
                ("project", project_id, json.dumps(props), 1, False),
            )
            obj_inserted += 1

    reg_actions = []
    for g_key, g in CORPORATE_GROUPS.items():
        if g["risk"] != "HIGH":
            continue
        for i, co in enumerate(g["companies"][:5]):
            action_id = f"RA-{g_key[:3].upper()}-{i+1:04d}"
            props = {
                "actionId": action_id, "entityCin": co["cin"],
                "regulatoryBodyId": random.choice(["SEBI", "RBI", "RERA", "ED", "CBI"]),
                "actionType": random.choice(["Penalty", "Show Cause Notice", "Debarment"]),
                "severity": "HIGH", "penaltyAmount": random.randint(500000, 500000000),
                "issueDate": rand_date(1000).date().isoformat(),
                "status": random.choice(["Active", "Appealed"]),
            }
            reg_actions.append((action_id, co["cin"]))
            cur.execute(
                """
                INSERT INTO ontology_objects (object_type, primary_key, properties, version, is_deleted)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (object_type, primary_key) DO UPDATE
                    SET properties = EXCLUDED.properties, updated_at = now()
                """,
                ("regulatory_action", action_id, json.dumps(props), 1, False),
            )
            obj_inserted += 1

    for i, co in enumerate(CORPORATE_GROUPS["reddy"]["companies"][:3]):
        cirp_id = f"CIRP-NCLT-{2020+i}-{100+i}"
        props = {
            "cirpId": cirp_id, "debtorCin": co["cin"],
            "ncltBench": random.choice(["NCLT Mumbai", "NCLT Hyderabad"]),
            "claimsAmount": random.randint(100000000, 10000000000),
            "status": random.choice(["Ongoing", "Liquidation"]),
        }
        cur.execute(
            """
            INSERT INTO ontology_objects (object_type, primary_key, properties, version, is_deleted)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (object_type, primary_key) DO UPDATE
                SET properties = EXCLUDED.properties, updated_at = now()
            """,
            ("insolvency_proceeding", cirp_id, json.dumps(props), 1, False),
        )
        obj_inserted += 1

    conn.commit()
    print(f"  Inserted/updated {obj_inserted} ontology objects")

    # -- Layer 3: ontology_links -----------------------------------------
    # id is serial integer — omit from INSERT; no unique constraint, plain INSERT
    link_inserted = 0
    # Clear existing links to avoid duplicates on re-run
    cur.execute("DELETE FROM ontology_links WHERE link_type IN ('DIRECTED', 'PROMOTES', 'SUBJECT_OF')")

    for g_key, g in CORPORATE_GROUPS.items():
        for d in g["directors"]:
            for co in random.sample(g["companies"], min(random.randint(2, 5), len(g["companies"]))):
                cur.execute(
                    """
                    INSERT INTO ontology_links
                        (link_type, source_type, source_id, target_type, target_id, properties, is_inferred)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    ("DIRECTED", "director", d["din"], "company", co["cin"],
                     json.dumps({"designation": random.choice(["Managing Director", "Director", "Independent Director"])}),
                     False),
                )
                link_inserted += 1

    for project_id, cin in project_records:
        cur.execute(
            """
            INSERT INTO ontology_links
                (link_type, source_type, source_id, target_type, target_id, properties, is_inferred)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            ("PROMOTES", "company", cin, "project", project_id, json.dumps({}), False),
        )
        link_inserted += 1

    for action_id, cin in reg_actions:
        cur.execute(
            """
            INSERT INTO ontology_links
                (link_type, source_type, source_id, target_type, target_id, properties, is_inferred)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            ("SUBJECT_OF", "company", cin, "regulatory_action", action_id, json.dumps({}), False),
        )
        link_inserted += 1

    conn.commit()
    print(f"  Inserted {link_inserted} ontology links")

    # -- Layer 3: ontology_events ----------------------------------------
    # Columns: id(uuid auto), occurred_at, object_type, object_id, event_type,
    #          property_name, old_value(jsonb), new_value(jsonb), actor_id, source, metadata
    events_inserted = 0
    EVENT_TYPES = ["CREATED", "UPDATED", "RISK_SCORE_CHANGED", "STATUS_CHANGED", "FLAGGED"]
    for g_key, co in _all_companies():
        for _ in range(random.randint(2, 5)):
            evt_type = random.choice(EVENT_TYPES)
            new_val = risk_score(g_key) if evt_type == "RISK_SCORE_CHANGED" else co["status"]
            cur.execute(
                """
                INSERT INTO ontology_events
                    (object_type, object_id, event_type, property_name,
                     old_value, new_value, actor_id, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ("company", co["cin"], evt_type,
                 "riskScore" if evt_type == "RISK_SCORE_CHANGED" else "status",
                 None, json.dumps(new_val), "system/l5-risk-engine", "l5_risk_engine"),
            )
            events_inserted += 1
    conn.commit()
    print(f"  Inserted {events_inserted} ontology events")

    # -- Layer 5: feature store ------------------------------------------
    # id is bigint serial; unique on (entity_type, entity_id, feature_name, computed_at)
    # Use a single fixed computed_at per run so re-runs conflict and don't stack
    feats_inserted = 0
    feat_ts = now_utc().replace(microsecond=0)
    for g_key, co in _all_companies():
        for feat in FEATURES:
            cur.execute(
                """
                INSERT INTO l5_feature_store
                    (entity_type, entity_id, feature_name, feature_value, computed_at, schema_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_type, entity_id, feature_name, computed_at) DO UPDATE
                    SET feature_value = EXCLUDED.feature_value
                """,
                ("company", co["cin"], feat, round(random.uniform(0, 1), 6), feat_ts, "v1.0"),
            )
            feats_inserted += 1

    for g_key, d in _all_directors():
        for feat in ["risk_score", "network_centrality", "director_overlap_count", "regulatory_exposure"]:
            cur.execute(
                """
                INSERT INTO l5_feature_store
                    (entity_type, entity_id, feature_name, feature_value, computed_at, schema_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_type, entity_id, feature_name, computed_at) DO UPDATE
                    SET feature_value = EXCLUDED.feature_value
                """,
                ("director", d["din"], feat, round(random.uniform(0, 1), 6), feat_ts, "v1.0"),
            )
            feats_inserted += 1
    conn.commit()
    print(f"  Inserted {feats_inserted} feature store rows")

    # -- Layer 5: models -------------------------------------------------
    # Columns: model_id(uuid), model_name, model_type, version, status, training_date,
    #          feature_schema_version, evaluation_metrics, model_artifact_path, hyperparameters,
    #          training_sample_size, created_at
    MODEL_DEFS = [
        ("cirp_precursor", "gradient_boosting", "v2.1.0", {"auc_roc": 0.89, "precision": 0.81, "recall": 0.77, "f1": 0.79}),
        ("project_completion", "random_forest", "v1.3.2", {"auc_roc": 0.84, "precision": 0.78, "recall": 0.80, "f1": 0.79}),
        ("regulatory_likelihood", "xgboost", "v1.0.5", {"auc_roc": 0.87, "precision": 0.75, "recall": 0.82, "f1": 0.78}),
        ("shell_company_detector", "neural_network", "v0.9.1", {"auc_roc": 0.91, "precision": 0.85, "recall": 0.73, "f1": 0.79}),
        ("network_anomaly", "isolation_forest", "v1.1.0", {"auc_roc": 0.79, "precision": 0.71, "recall": 0.84, "f1": 0.77}),
    ]
    model_ids: dict[str, str] = {}
    for m_name, m_type, m_ver, metrics in MODEL_DEFS:
        cur.execute(
            """
            INSERT INTO l5_models
                (model_id, model_name, model_type, version, status, training_date,
                 feature_schema_version, evaluation_metrics, training_sample_size)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_name, version) DO UPDATE
                SET evaluation_metrics = EXCLUDED.evaluation_metrics
            RETURNING model_id
            """,
            (str(uuid.uuid4()), m_name, m_type, m_ver, "active",
             rand_date(90, 7), "v1.0", json.dumps(metrics), 5000),
        )
        row = cur.fetchone()
        model_ids[m_name] = str(row[0])
    conn.commit()
    print(f"  Inserted {len(MODEL_DEFS)} models")

    # -- Layer 5: predictions --------------------------------------------
    # id is bigint serial; no unique constraint — plain INSERT
    pred_inserted = 0
    for g_key, co in _all_companies():
        score = risk_score(g_key)
        for m_name, m_id in model_ids.items():
            pred_val = score if any(k in m_name for k in ("risk", "cirp", "shell", "regulatory")) else round(random.uniform(0, 1), 4)
            shap = {feat: round(random.uniform(-0.2, 0.3), 4) for feat in FEATURES[:5]}
            cur.execute(
                """
                INSERT INTO l5_predictions
                    (model_id, entity_type, entity_id, prediction_value, shap_values, feature_snapshot)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (m_id, "company", co["cin"], pred_val, json.dumps(shap), json.dumps({})),
            )
            pred_inserted += 1
    conn.commit()
    print(f"  Inserted {pred_inserted} predictions")

    # -- Layer 5: LLM audit logs -----------------------------------------
    # id is bigint serial; columns: workflow_type, actor_id, actor_role, model_used,
    #   prompt_tokens, completion_tokens, objects_accessed, output_disposition,
    #   prompt_hash, success, latency_ms, error_message, created_at
    WORKFLOWS = ["narrative", "report", "agent", "extraction", "summarization"]
    llm_inserted = 0
    for _ in range(200):
        prompt_tokens = random.randint(200, 4000)
        completion_tokens = random.randint(100, 2000)
        cur.execute(
            """
            INSERT INTO l5_llm_audit
                (workflow_type, actor_id, actor_role, model_used,
                 prompt_tokens, completion_tokens, success, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (random.choice(WORKFLOWS), f"user:{uuid.uuid4().hex[:8]}", "analyst",
             "qwen3:8b", prompt_tokens, completion_tokens,
             True, random.randint(500, 8000)),
        )
        llm_inserted += 1
    conn.commit()
    print(f"  Inserted {llm_inserted} LLM audit logs")

    # -- Layer 5: agent runs ---------------------------------------------
    # id is bigint serial; run_id is uuid unique; columns: run_id, agent_type, actor_id,
    #   input_params, execution_trace, output_summary, status, total_tokens,
    #   total_latency_ms, guardrail_triggers, created_at, completed_at
    AGENT_TYPES = ["risk_investigator", "compliance_checker", "network_analyzer", "report_generator"]
    for _ in range(50):
        g_key = random.choice(list(CORPORATE_GROUPS.keys()))
        co = random.choice(CORPORATE_GROUPS[g_key]["companies"])
        created = now_utc() - timedelta(hours=random.randint(1, 48))
        cur.execute(
            """
            INSERT INTO l5_agent_runs
                (run_id, agent_type, actor_id, input_params, execution_trace,
                 output_summary, status, total_tokens, total_latency_ms, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), random.choice(AGENT_TYPES),
             "analyst@satorix.internal",
             json.dumps({"cin": co["cin"], "depth": 2}),
             json.dumps([]),
             f"Analysis of {co['name']} complete. Risk: {CORPORATE_GROUPS[g_key]['risk']}",
             "completed", random.randint(500, 5000), random.randint(2000, 30000),
             created + timedelta(minutes=random.randint(1, 30))),
        )
    conn.commit()
    print("  Inserted 50 agent runs")

    # -- Layer 5: correlations -------------------------------------------
    # unique on (feature_a, feature_b, lag_periods, entity_type)
    for i, fa in enumerate(FEATURES):
        for fb in FEATURES[i+1:]:
            corr = round(random.uniform(-0.8, 0.9), 4)
            cur.execute(
                """
                INSERT INTO l5_correlations
                    (feature_a, feature_b, correlation_coefficient, p_value, sample_size,
                     lag_periods, entity_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (feature_a, feature_b, lag_periods, entity_type) DO UPDATE
                    SET correlation_coefficient = EXCLUDED.correlation_coefficient
                """,
                (fa, fb, corr, round(random.uniform(0.001, 0.05), 4), 50, 0, "Company"),
            )
    conn.commit()
    print("  Inserted feature correlations")

    # -- Layer 6: users --------------------------------------------------
    # Columns: id, email, name, password_hash, role, client_id, is_active, created_at, last_login
    USERS = [
        ("admin@satorix.internal", "Platform Administrator", "platform_administrator", "satorix_internal", "SatorixAdmin2026!"),
        ("analyst@satorix.internal", "Senior Risk Analyst", "risk_analyst", "satorix_internal", "Analyst@2026"),
        ("compliance@satorix.internal", "Compliance Officer", "compliance_officer", "satorix_internal", "Comply@2026"),
        ("readonly@satorix.internal", "Read Only User", "viewer", "satorix_internal", "Viewer@2026"),
        ("analyst2@satorix.internal", "Junior Analyst", "risk_analyst", "satorix_internal", "Junior@2026"),
        ("designer@satorix.internal", "Ontology Designer", "ontology_designer", "satorix_internal", "Design@2026"),
    ]
    user_ids: dict[str, str] = {}
    for email, name, role, client_id, password in USERS:
        cur.execute("SELECT id FROM l6_users WHERE email = %s", (email,))
        row = cur.fetchone()
        if row:
            user_ids[email] = str(row[0])
        else:
            pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            user_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO l6_users (id, email, name, password_hash, role, client_id, is_active, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                (user_id, email, name, pwd_hash, role, client_id, True, now_utc()),
            )
            user_ids[email] = user_id
    conn.commit()
    print(f"  Inserted/ensured {len(USERS)} users")

    # -- Layer 6: watchlists ---------------------------------------------
    # Columns: id, user_id, entity_type, entity_id, entity_name, added_at, notes
    # unique on (user_id, entity_type, entity_id)
    analyst_id = user_ids.get("analyst@satorix.internal")
    if analyst_id:
        for g_key, co in list(_all_companies())[:10]:
            cur.execute(
                """
                INSERT INTO l6_watchlists (id, user_id, entity_type, entity_id, entity_name, added_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, entity_type, entity_id) DO NOTHING
                """,
                (str(uuid.uuid4()), analyst_id, "company", co["cin"], co["name"], now_utc()),
            )
        for g_key, d in list(_all_directors())[:5]:
            cur.execute(
                """
                INSERT INTO l6_watchlists (id, user_id, entity_type, entity_id, entity_name, added_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, entity_type, entity_id) DO NOTHING
                """,
                (str(uuid.uuid4()), analyst_id, "director", d["din"], d["name"], now_utc()),
            )
        conn.commit()
        print("  Inserted watchlists for analyst user")

    cur.close()
    conn.close()
    print("PostgreSQL: DONE")


# ---------------------------------------------------------------------------
# Neo4j population
# ---------------------------------------------------------------------------

def populate_neo4j():
    print("\n=== Neo4j ===")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    with driver.session() as session:
        # Companies
        for g_key, co in _all_companies():
            band = CORPORATE_GROUPS[g_key]["risk"]
            score = risk_score(g_key)
            session.run(
                """
                MERGE (n:Company {cin: $cin})
                SET n += {
                    name: $name, state: $state, status: $status,
                    sector: $sector, riskScore: $riskScore, riskBand: $riskBand,
                    isAnomalous: $isAnomalous, object_type: 'company',
                    incorporationDate: $incDate, group: $group
                }
                """,
                cin=co["cin"], name=co["name"], state=co["state"],
                status=co["status"], sector=CORPORATE_GROUPS[g_key]["sector"],
                riskScore=score, riskBand=band, isAnomalous=(band == "HIGH"),
                incDate=rand_date(8000, 1000).date().isoformat(),
                group=CORPORATE_GROUPS[g_key]["display"],
            )
        print("  Upserted 50 Company nodes")

        # Directors
        for g_key, d in _all_directors():
            band = CORPORATE_GROUPS[g_key]["risk"]
            score = risk_score(g_key)
            session.run(
                """
                MERGE (n:Director {din: $din})
                SET n += {
                    name: $name, nationality: $nationality,
                    riskScore: $riskScore, riskBand: $riskBand,
                    isAnomalous: $isAnomalous, object_type: 'director',
                    group: $group
                }
                """,
                din=d["din"], name=d["name"], nationality=d["nationality"],
                riskScore=score, riskBand=band, isAnomalous=(band == "HIGH"),
                group=CORPORATE_GROUPS[g_key]["display"],
            )
        print("  Upserted 80 Director nodes")

        # DIRECTED relationships
        dir_rels = 0
        for g_key, g in CORPORATE_GROUPS.items():
            for d in g["directors"]:
                n_cos = random.randint(2, 5)
                for co in random.sample(g["companies"], min(n_cos, len(g["companies"]))):
                    session.run(
                        """
                        MATCH (d:Director {din: $din})
                        MATCH (c:Company {cin: $cin})
                        MERGE (d)-[r:DIRECTED]->(c)
                        SET r.designation = $designation,
                            r.appointmentDate = $apptDate
                        """,
                        din=d["din"], cin=co["cin"],
                        designation=random.choice(["Managing Director", "Director", "Independent Director", "Whole Time Director"]),
                        apptDate=rand_date(3000, 30).date().isoformat(),
                    )
                    dir_rels += 1
        print(f"  Created ~{dir_rels} DIRECTED relationships")

        # Projects
        for g_key, g in CORPORATE_GROUPS.items():
            band = g["risk"]
            for i in range(7):
                co = g["companies"][i % len(g["companies"])]
                project_id = f"RERA-{co['state']}-{g_key[:3].upper()}-{i+1:04d}"
                status = random.choice(PROJECT_STATUSES)
                score = risk_score(g_key)
                session.run(
                    """
                    MERGE (p:Project {projectId: $projectId})
                    SET p += {
                        name: $name, reraState: $state, status: $status,
                        riskScore: $riskScore, riskBand: $riskBand,
                        promoterCin: $cin, object_type: 'project',
                        sanctionedUnits: $units, isDelayed: $delayed
                    }
                    WITH p
                    MATCH (c:Company {cin: $cin})
                    MERGE (c)-[r:PROMOTES]->(p)
                    """,
                    projectId=project_id,
                    name=f"{g['display']} Phase {i+1}",
                    state=co["state"], status=status,
                    riskScore=score, riskBand=band,
                    cin=co["cin"], units=random.randint(50, 2000),
                    delayed=(status in ["Delayed", "On Hold"]),
                )
        print("  Upserted 35 Project nodes + PROMOTES relationships")

        # Regulatory Actions for HIGH-risk groups
        for g_key, g in CORPORATE_GROUPS.items():
            if g["risk"] != "HIGH":
                continue
            for i, co in enumerate(g["companies"][:5]):
                action_id = f"RA-{g_key[:3].upper()}-{i+1:04d}"
                session.run(
                    """
                    MERGE (r:RegulatoryAction {actionId: $actionId})
                    SET r += {
                        actionType: $actionType, severity: $sev,
                        penaltyAmount: $amount, entityCin: $cin,
                        object_type: 'regulatory_action', status: $status
                    }
                    WITH r
                    MATCH (c:Company {cin: $cin})
                    MERGE (c)-[rel:SUBJECT_OF]->(r)
                    """,
                    actionId=action_id,
                    actionType=random.choice(["Penalty", "Show Cause Notice", "Debarment"]),
                    sev="HIGH", amount=random.randint(500000, 500000000),
                    cin=co["cin"], status=random.choice(["Active", "Appealed"]),
                )
        print("  Upserted RegulatoryAction nodes + SUBJECT_OF relationships")

        # Insolvency proceedings for Reddy
        for i, co in enumerate(CORPORATE_GROUPS["reddy"]["companies"][:3]):
            cirp_id = f"CIRP-NCLT-{2020+i}-{random.randint(100, 999)}"
            session.run(
                """
                MERGE (ip:InsolvencyProceeding {cirpId: $cirpId})
                SET ip += {
                    ncltBench: $bench, claimsAmount: $claims,
                    status: $status, object_type: 'insolvency_proceeding',
                    debtorCin: $cin
                }
                WITH ip
                MATCH (c:Company {cin: $cin})
                MERGE (c)-[r:SUBJECT_OF]->(ip)
                """,
                cirpId=cirp_id,
                bench=random.choice(["NCLT Mumbai", "NCLT Hyderabad"]),
                claims=random.randint(100000000, 10000000000),
                status=random.choice(["Ongoing", "Liquidation"]),
                cin=co["cin"],
            )
        print("  Upserted InsolvencyProceeding nodes")

        # SHARES_DIRECTOR inferred links between companies sharing directors
        session.run(
            """
            MATCH (c1:Company)<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(c2:Company)
            WHERE id(c1) < id(c2)
            MERGE (c1)-[r:SHARES_DIRECTOR]->(c2)
            SET r.isInferred = true, r.directorDin = d.din
            """
        )
        print("  Created SHARES_DIRECTOR inferred relationships")

        # Alerts for HIGH-risk entities
        for g_key, g in CORPORATE_GROUPS.items():
            if g["risk"] != "HIGH":
                continue
            for i, co in enumerate(g["companies"][:3]):
                alert_id = f"ALERT-{g_key[:3].upper()}-{i+1:04d}"
                session.run(
                    """
                    MERGE (a:Alert {alertId: $alertId})
                    SET a += {
                        alertType: $alertType, severity: 'HIGH',
                        entityCin: $cin, isAcknowledged: false,
                        object_type: 'alert', message: $msg
                    }
                    WITH a
                    MATCH (c:Company {cin: $cin})
                    MERGE (c)-[r:HAS_ALERT]->(a)
                    """,
                    alertId=alert_id,
                    alertType=random.choice(["RISK_THRESHOLD_BREACH", "REGULATORY_ACTION", "RERA_DELAY", "DIRECTOR_DEBARMENT"]),
                    cin=co["cin"],
                    msg=f"High-risk alert for {co['name']}",
                )
        print("  Upserted Alert nodes + HAS_ALERT relationships")

    driver.close()
    print("Neo4j: DONE")


# ---------------------------------------------------------------------------
# Elasticsearch population
# ---------------------------------------------------------------------------

def populate_elasticsearch():
    print("\n=== Elasticsearch ===")
    es = Elasticsearch(ES_HOST)

    INDICES = {
        "ontology_company": "company",
        "ontology_director": "director",
        "ontology_project": "project",
        "ontology_regulatory_action": "regulatory_action",
        "ontology_insolvency_proceeding": "insolvency_proceeding",
        "ontology_alert": "alert",
    }

    for idx, obj_type in INDICES.items():
        if not es.indices.exists(index=idx):
            es.indices.create(index=idx, body={"mappings": {"properties": {"name": {"type": "text"}, "object_type": {"type": "keyword"}}}})

    bulk_ops = []
    count = 0

    for g_key, co in _all_companies():
        band = CORPORATE_GROUPS[g_key]["risk"]
        score = risk_score(g_key)
        bulk_ops.append({"index": {"_index": "ontology_company", "_id": co["cin"]}})
        bulk_ops.append({
            "object_type": "company", "cin": co["cin"], "name": co["name"],
            "state": co["state"], "status": co["status"],
            "sector": CORPORATE_GROUPS[g_key]["sector"],
            "riskScore": score, "riskBand": band,
            "group": CORPORATE_GROUPS[g_key]["display"],
            "isAnomalous": band == "HIGH",
            "updated_at": now_utc().isoformat(),
        })
        count += 1

    for g_key, d in _all_directors():
        band = CORPORATE_GROUPS[g_key]["risk"]
        score = risk_score(g_key)
        bulk_ops.append({"index": {"_index": "ontology_director", "_id": d["din"]}})
        bulk_ops.append({
            "object_type": "director", "din": d["din"], "name": d["name"],
            "nationality": d["nationality"], "riskScore": score, "riskBand": band,
            "group": CORPORATE_GROUPS[g_key]["display"],
            "isAnomalous": band == "HIGH",
            "updated_at": now_utc().isoformat(),
        })
        count += 1

    for g_key, g in CORPORATE_GROUPS.items():
        band = g["risk"]
        for i in range(7):
            co = g["companies"][i % len(g["companies"])]
            project_id = f"RERA-{co['state']}-{g_key[:3].upper()}-{i+1:04d}"
            status = random.choice(PROJECT_STATUSES)
            bulk_ops.append({"index": {"_index": "ontology_project", "_id": project_id}})
            bulk_ops.append({
                "object_type": "project", "projectId": project_id,
                "name": f"{g['display']} Phase {i+1}", "status": status,
                "riskBand": band, "promoterCin": co["cin"],
                "reraState": co["state"], "updated_at": now_utc().isoformat(),
            })
            count += 1

    if bulk_ops:
        resp = es.bulk(operations=bulk_ops, refresh=True)
        if resp.get("errors"):
            print(f"  WARNING: some ES bulk errors occurred")
        else:
            print(f"  Indexed {count} documents across indices")

    print("Elasticsearch: DONE")


# ---------------------------------------------------------------------------
# Redis population
# ---------------------------------------------------------------------------

def populate_redis():
    print("\n=== Redis ===")
    try:
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
    except Exception as e:
        print(f"  Redis unavailable: {e} — skipping")
        return

    inserted = 0

    # Entity risk score cache
    for g_key, co in _all_companies():
        score = risk_score(g_key)
        band = CORPORATE_GROUPS[g_key]["risk"]
        key = f"risk:company:{co['cin']}"
        r.setex(key, 3600, json.dumps({"riskScore": score, "riskBand": band, "name": co["name"]}))
        inserted += 1

    for g_key, d in _all_directors():
        score = risk_score(g_key)
        band = CORPORATE_GROUPS[g_key]["risk"]
        key = f"risk:director:{d['din']}"
        r.setex(key, 3600, json.dumps({"riskScore": score, "riskBand": band, "name": d["name"]}))
        inserted += 1

    # Session tokens for L6 users
    for email in ["admin@satorix.internal", "analyst@satorix.internal"]:
        token = uuid.uuid4().hex
        r.setex(f"session:{token}", 86400, json.dumps({"email": email, "role": "analyst"}))

    # Search autocomplete cache
    company_names = [co["name"] for _, co in _all_companies()]
    r.delete("autocomplete:company")
    for name in company_names[:20]:
        r.zadd("autocomplete:company", {name: 0})

    # Recent searches ring
    r.delete("recent:searches")
    for g_key, co in list(_all_companies())[:10]:
        r.lpush("recent:searches", json.dumps({"type": "company", "id": co["cin"], "name": co["name"]}))
    r.ltrim("recent:searches", 0, 49)

    # Service health cache
    for svc in ["layer1-api", "layer2-api", "layer3-api", "layer4-api", "layer5-api"]:
        r.setex(f"health:{svc}", 300, json.dumps({"status": "healthy", "response_time_ms": random.randint(10, 120)}))

    print(f"  Set {inserted} risk score cache entries + session tokens + autocomplete")
    print("Redis: DONE")


# ---------------------------------------------------------------------------
# Kafka population
# ---------------------------------------------------------------------------

def populate_kafka():
    print("\n=== Kafka ===")
    try:
        producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP],
            value_serializer=lambda v: json.dumps(v).encode(),
            request_timeout_ms=5000,
            connections_max_idle_ms=10000,
        )
    except Exception as e:
        print(f"  Kafka unavailable: {e} — skipping")
        return

    sent = 0

    # layer1.raw.parquet.ready
    for g_key, co in list(_all_companies())[:15]:
        msg = {
            "event": "parquet.ready", "cin": co["cin"], "source": "mca21_corporate_registry",
            "batch_id": str(uuid.uuid4()), "record_count": random.randint(100, 5000),
            "s3_path": f"s3://raw-data/mca21/{now_utc().date()}/{co['cin']}.parquet",
            "timestamp": now_utc().isoformat(),
        }
        producer.send("layer1.raw.parquet.ready", msg)
        sent += 1

    # layer2.clean.ready
    for g_key, co in list(_all_companies())[:15]:
        msg = {
            "event": "clean.ready", "object_type": "company", "primary_key": co["cin"],
            "batch_id": str(uuid.uuid4()), "pipeline": "mca21_company_normalizer",
            "timestamp": now_utc().isoformat(),
        }
        producer.send("layer2.clean.ready", msg)
        sent += 1

    # layer3.ontology.changes
    for g_key, co in list(_all_companies())[:20]:
        msg = {
            "event": "entity.updated", "object_type": "company", "primary_key": co["cin"],
            "changed_fields": ["riskScore", "status"],
            "actor": "system/l5-risk-engine", "timestamp": now_utc().isoformat(),
        }
        producer.send("layer3.ontology.changes", msg)
        sent += 1

    # layer3.alerts.created
    for g_key, g in CORPORATE_GROUPS.items():
        if g["risk"] != "HIGH":
            continue
        for co in g["companies"][:2]:
            msg = {
                "event": "alert.created",
                "alert_id": f"ALERT-{g_key[:3].upper()}-{random.randint(1000, 9999)}",
                "entity_type": "company", "entity_id": co["cin"],
                "severity": "HIGH", "alert_type": "RISK_THRESHOLD_BREACH",
                "timestamp": now_utc().isoformat(),
            }
            producer.send("layer3.alerts.created", msg)
            sent += 1

    # layer3.ingest.complete
    msg = {
        "event": "ingest.complete", "source": "mca21_corporate_registry",
        "records_ingested": 15000, "timestamp": now_utc().isoformat(),
    }
    producer.send("layer3.ingest.complete", msg)
    sent += 1

    # layer4.recompute.triggers
    for g_key, co in list(_all_companies())[:10]:
        msg = {
            "event": "recompute.trigger", "entity_type": "company", "entity_id": co["cin"],
            "reason": "risk_score_updated", "timestamp": now_utc().isoformat(),
        }
        producer.send("layer4.recompute.triggers", msg)
        sent += 1

    # layer5.risk.scores.updated
    for g_key, co in list(_all_companies())[:20]:
        score = risk_score(g_key)
        msg = {
            "event": "risk.score.updated", "entity_type": "company", "entity_id": co["cin"],
            "new_score": score, "model": "cirp_precursor",
            "timestamp": now_utc().isoformat(),
        }
        producer.send("layer5.risk.scores.updated", msg)
        sent += 1

    # layer5.predictions.ready
    msg = {
        "event": "predictions.ready", "model": "cirp_precursor",
        "entity_count": 50, "batch_id": str(uuid.uuid4()),
        "timestamp": now_utc().isoformat(),
    }
    producer.send("layer5.predictions.ready", msg)
    sent += 1

    producer.flush()
    producer.close()
    print(f"  Published {sent} messages across topics")
    print("Kafka: DONE")


# ---------------------------------------------------------------------------
# MinIO population
# ---------------------------------------------------------------------------

def populate_minio():
    print("\n=== MinIO ===")
    try:
        client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS, secret_key=MINIO_SECRET, secure=False)
    except Exception as e:
        print(f"  MinIO unavailable: {e} — skipping")
        return

    BUCKETS = ["raw-data", "processed-data", "model-artifacts", "profiling-reports"]
    for bucket in BUCKETS:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)

    import io

    uploaded = 0

    # Parquet files in raw-data and processed-data
    for g_key, co in list(_all_companies())[:10]:
        df = pd.DataFrame([{
            "cin": co["cin"], "name": co["name"], "state": co["state"],
            "status": co["status"], "sector": CORPORATE_GROUPS[g_key]["sector"],
            "riskScore": risk_score(g_key), "extractedAt": now_utc().isoformat(),
        }])
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        data = buf.read()
        path = f"mca21/{now_utc().date()}/{co['cin']}.parquet"
        client.put_object("raw-data", path, io.BytesIO(data), length=len(data), content_type="application/octet-stream")
        uploaded += 1

    # Director parquet
    dir_df = pd.DataFrame([
        {"din": d["din"], "name": d["name"], "nationality": d["nationality"],
         "group": CORPORATE_GROUPS[g_key]["display"]}
        for g_key, d in list(_all_directors())[:20]
    ])
    buf = io.BytesIO()
    dir_df.to_parquet(buf, index=False)
    buf.seek(0)
    data = buf.read()
    client.put_object("processed-data", f"directors/{now_utc().date()}/directors.parquet",
                      io.BytesIO(data), length=len(data), content_type="application/octet-stream")
    uploaded += 1

    # Model artifacts
    for model_name in ["cirp_precursor_v2.1.0", "project_completion_v1.3.2", "regulatory_likelihood_v1.0.5"]:
        artifact = json.dumps({
            "model_name": model_name, "framework": "sklearn",
            "created_at": now_utc().isoformat(),
            "hyperparameters": {"n_estimators": 200, "max_depth": 8, "learning_rate": 0.05},
            "features": ["risk_score", "network_centrality", "regulatory_action_count"],
        }).encode()
        path = f"models/{model_name}/metadata.json"
        client.put_object("model-artifacts", path, io.BytesIO(artifact),
                          length=len(artifact), content_type="application/json")
        uploaded += 1

    # Profiling reports (JSON)
    for g_key, co in list(_all_companies())[:5]:
        report = json.dumps({
            "cin": co["cin"], "name": co["name"],
            "risk_score": risk_score(g_key), "report_date": now_utc().date().isoformat(),
            "findings": [f"Network centrality: {round(random.uniform(0, 1), 3)}",
                         f"Director overlap: {random.randint(2, 8)} companies"],
        }).encode()
        path = f"companies/{co['cin']}/profile_{now_utc().date()}.json"
        client.put_object("profiling-reports", path, io.BytesIO(report),
                          length=len(report), content_type="application/json")
        uploaded += 1

    print(f"  Uploaded {uploaded} objects to MinIO")
    print("MinIO: DONE")


# ---------------------------------------------------------------------------
# Airflow: trigger DAG runs
# ---------------------------------------------------------------------------

def populate_airflow():
    print("\n=== Airflow ===")
    try:
        import httpx
        client = httpx.Client(base_url=AIRFLOW_URL, auth=(AIRFLOW_USER, AIRFLOW_PASS), timeout=10)
        resp = client.get("/api/v1/dags")
        if resp.status_code >= 400:
            raise Exception(f"Airflow returned {resp.status_code}")
    except Exception as e:
        print(f"  Airflow unavailable: {e} — skipping")
        return

    try:
        dags_resp = client.get("/api/v1/dags")
        if dags_resp.status_code < 400:
            dags = dags_resp.json().get("dags", [])
            print(f"  Found {len(dags)} DAGs")
            for dag in dags:
                dag_id = dag["dag_id"]
                # Unpause each DAG
                client.patch(f"/api/v1/dags/{dag_id}", json={"is_paused": False})
                # Trigger one historical run
                run_resp = client.post(
                    f"/api/v1/dags/{dag_id}/dagRuns",
                    json={
                        "dag_run_id": f"mock_{dag_id}_{int(time.time())}",
                        "conf": {"triggered_by": "mock_data_generator"},
                    },
                )
                if run_resp.status_code in (200, 409):
                    print(f"  Triggered DAG: {dag_id}")
                else:
                    print(f"  DAG trigger failed for {dag_id}: {run_resp.status_code}")
    except Exception as e:
        print(f"  Airflow DAG trigger error: {e}")

    client.close()
    print("Airflow: DONE")


# ---------------------------------------------------------------------------
# Ollama: verify model availability
# ---------------------------------------------------------------------------

def test_ollama():
    print("\n=== Ollama ===")
    try:
        import httpx
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code < 400:
            models = [m["name"] for m in resp.json().get("models", [])]
            print(f"  Available models: {models}")
            if "qwen3:8b" in models or any("qwen3" in m for m in models):
                print("  qwen3:8b model present — running test inference")
                gen = httpx.post(
                    f"{OLLAMA_URL}/api/generate",
                    json={"model": "qwen3:8b", "prompt": "Respond with exactly: MOCK_OK", "stream": False},
                    timeout=30,
                )
                if gen.status_code < 400:
                    print(f"  Test inference response: {gen.json().get('response', '').strip()[:50]}")
            else:
                print("  WARNING: qwen3:8b not found — layer5 LLM workflows may fail")
        else:
            print(f"  Ollama returned {resp.status_code}")
    except Exception as e:
        print(f"  Ollama unavailable: {e} — skipping")

    print("Ollama: DONE")


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

class MockDataGenerator:
    def run(self):
        print("=" * 60)
        print("Satorix Mock Data Generator")
        print(f"Corporate groups: {len(CORPORATE_GROUPS)}")
        print(f"Companies: {sum(len(g['companies']) for g in CORPORATE_GROUPS.values())}")
        print(f"Directors: {sum(len(g['directors']) for g in CORPORATE_GROUPS.values())}")
        print("=" * 60)

        steps = [
            ("PostgreSQL", populate_postgresql),
            ("Neo4j", populate_neo4j),
            ("Elasticsearch", populate_elasticsearch),
            ("Redis", populate_redis),
            ("Kafka", populate_kafka),
            ("MinIO", populate_minio),
            ("Airflow", populate_airflow),
            ("Ollama", test_ollama),
        ]

        for name, fn in steps:
            try:
                fn()
            except Exception as e:
                print(f"\n  ERROR in {name}: {e}")
                import traceback
                traceback.print_exc()

        print("\n" + "=" * 60)
        print("Mock data generation COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    generator = MockDataGenerator()
    generator.run()

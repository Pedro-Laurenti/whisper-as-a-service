import os
import secrets
import hashlib
from typing import List, Dict, Any, Optional
import asyncpg
import datetime
from ipaddress import ip_address, ip_network
from dotenv import load_dotenv
from src.init_db import get_db_conn

load_dotenv()

# Variáveis de conexão com o banco de dados são importadas do módulo init_db

def hash_api_key(key: str) -> str:
    """Cria um hash da API Key para armazenamento seguro."""
    return hashlib.sha256(key.encode()).hexdigest()

async def generate_api_key(name: str, expires_days: int = 365, allowed_ips: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Gera uma nova API Key e a armazena no banco de dados.
    
    Args:
        name: Nome descritivo para identificar a API Key
        expires_days: Validade em dias
        allowed_ips: Lista opcional de IPs ou CIDRs com permissão para usar esta chave
    
    Returns:
        Dicionário com informações sobre a API Key gerada
    """
    # Gera uma chave aleatória de 32 bytes (64 caracteres em hex)
    api_key = secrets.token_hex(32)
    key_hash = hash_api_key(api_key)
    
    # Calcula a data de expiração
    expires_at = datetime.datetime.now() + datetime.timedelta(days=expires_days) if expires_days else None
    
    # Insere no banco de dados
    conn = await get_db_conn()
    try:
        result = await conn.fetchrow(
            """
            INSERT INTO api_keys (key_hash, name, expires_at, allowed_ips)
            VALUES ($1, $2, $3, $4)
            RETURNING id, name, created_at, expires_at, is_active, allowed_ips
            """,
            key_hash, name, expires_at, allowed_ips
        )
        
        return {
            "id": result["id"],
            "api_key": api_key,  # Retornamos a chave apenas neste momento; depois só teremos o hash
            "name": result["name"],
            "created_at": result["created_at"].isoformat(),
            "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None,
            "is_active": result["is_active"],
            "allowed_ips": result["allowed_ips"]
        }
    finally:
        await conn.close()

async def validate_api_key(api_key: str, client_ip: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Valida uma API Key e atualiza estatísticas de uso.
    
    Args:
        api_key: A API Key a ser validada
        client_ip: Endereço IP do cliente (opcional)
    
    Returns:
        Dicionário com informações sobre a API Key se for válida, None caso contrário
    """
    if not api_key:
        return None
    
    key_hash = hash_api_key(api_key)
    
    conn = await get_db_conn()
    try:
        # Busca a API Key e verifica se é válida
        result = await conn.fetchrow(
            """
            SELECT id, name, created_at, expires_at, is_active, use_count, allowed_ips
            FROM api_keys
            WHERE key_hash = $1
            """,
            key_hash
        )
        
        if not result:
            return None
            
        # Verifica se a chave está ativa
        if not result["is_active"]:
            return None
            
        # Verifica se a chave expirou
        if result["expires_at"] and datetime.datetime.now() > result["expires_at"]:
            # Atualiza o status da chave para inativa
            await conn.execute(
                "UPDATE api_keys SET is_active = FALSE WHERE id = $1",
                result["id"]
            )
            return None
            
        # Verifica as restrições de IP, se houver
        if result["allowed_ips"] and client_ip:
            client_ip_obj = ip_address(client_ip)
            ip_allowed = False
            
            for allowed_ip in result["allowed_ips"]:
                # Verifica se é um IP único ou uma rede CIDR
                if "/" in allowed_ip:
                    # É uma rede CIDR
                    if client_ip_obj in ip_network(allowed_ip, strict=False):
                        ip_allowed = True
                        break
                else:
                    # É um IP único
                    if client_ip == allowed_ip:
                        ip_allowed = True
                        break
                        
            if not ip_allowed:
                return None
        
        # Atualiza as estatísticas de uso
        await conn.execute(
            """
            UPDATE api_keys SET 
                last_used_at = NOW(),
                use_count = use_count + 1
            WHERE id = $1
            """,
            result["id"]
        )
        
        return {
            "id": result["id"],
            "name": result["name"],
            "created_at": result["created_at"].isoformat(),
            "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None,
            "is_active": result["is_active"],
            "use_count": result["use_count"],
            "allowed_ips": result["allowed_ips"]
        }
    finally:
        await conn.close()

async def get_api_keys(active_only: bool = False) -> List[Dict[str, Any]]:
    """
    Retorna a lista de API Keys cadastradas.
    
    Args:
        active_only: Se True, retorna apenas keys ativas
    
    Returns:
        Lista de API Keys cadastradas
    """
    conn = await get_db_conn()
    try:
        query = """
            SELECT id, name, created_at, expires_at, is_active, last_used_at, use_count, allowed_ips
            FROM api_keys
        """
        
        if active_only:
            query += " WHERE is_active = TRUE"
            
        results = await conn.fetch(query)
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"].isoformat(),
                "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
                "is_active": row["is_active"],
                "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
                "use_count": row["use_count"],
                "allowed_ips": row["allowed_ips"]
            }
            for row in results
        ]
    finally:
        await conn.close()

async def revoke_api_key(key_id: int) -> bool:
    """
    Revoga (desativa) uma API Key.
    
    Args:
        key_id: ID da API Key a ser revogada
    
    Returns:
        True se a API Key foi revogada com sucesso, False caso contrário
    """
    conn = await get_db_conn()
    try:
        result = await conn.execute(
            "UPDATE api_keys SET is_active = FALSE WHERE id = $1",
            key_id
        )
        
        return "UPDATE 1" in result
    finally:
        await conn.close()

async def get_api_key(api_key_header: str, request = None) -> str:
    """
    Middleware para FastAPI que valida uma API Key.
    
    Args:
        api_key_header: Valor do cabeçalho X-API-Key
        request: Request do FastAPI (opcional)
    
    Returns:
        A API Key validada
    
    Raises:
        HTTPException: Se a API Key for inválida
    """
    from fastapi import HTTPException
    
    client_ip = None
    if request:
        client_ip = request.client.host
    
    result = await validate_api_key(api_key_header, client_ip)
    
    if not result:
        raise HTTPException(
            status_code=401,
            detail="API Key inválida ou expirada"
        )
    
    return api_key_header

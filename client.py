#!/usr/bin/env python3
import requests
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description='Cliente para teste da API de Transcrição de Áudio')
    parser.add_argument('--url', default='http://localhost:8001', help='URL base da API')
    parser.add_argument('--api-key', required=True, help='API Key para autenticação')
    parser.add_argument('--file', required=True, help='Caminho para o arquivo de áudio')
    parser.add_argument('--idioma', default=None, help='Idioma do áudio (opcional)')
    parser.add_argument('--modo', choices=['sincrono', 'assincrono'], default='assincrono', 
                        help='Modo de processamento: sincrono ou assincrono')
    
    args = parser.parse_args()
    
    # Verifica se o arquivo existe
    if not os.path.isfile(args.file):
        print(f"Erro: Arquivo '{args.file}' não encontrado")
        return
    
    # Prepara o cabeçalho com a API Key
    headers = {
        'X-API-Key': args.api_key
    }
    
    # Prepara o arquivo e dados para envio
    with open(args.file, 'rb') as f:
        files = {
            'file': (os.path.basename(args.file), f, 'audio/mpeg')
        }
        
        data = {}
        if args.idioma:
            data['idioma'] = args.idioma
        
        # Determina o endpoint com base no modo
        if args.modo == 'sincrono':
            url = f"{args.url}/transcribe"
            print(f"Enviando arquivo para transcrição síncrona...")
        else:
            url = f"{args.url}/transcribe/async"
            print(f"Enviando arquivo para transcrição assíncrona...")
        
        # Faz a requisição
        response = requests.post(url, headers=headers, files=files, data=data)
        
        # Processa a resposta
        if response.status_code == 200:
            result = response.json()
            
            if args.modo == 'sincrono':
                print("\n=== Transcrição Concluída ===")
                print(f"Idioma detectado: {result.get('idioma_detectado', 'desconhecido')}")
                print(f"Duração: {result.get('duracao', 0):.2f} segundos")
                print("\nTexto transcrito:")
                print("-" * 50)
                print(result.get('texto', ''))
                print("-" * 50)
            else:
                print("\n=== Transcrição Enfileirada ===")
                print(f"ID da transcrição: {result.get('id')}")
                print(f"Status: {result.get('status')}")
                print(f"Arquivo: {result.get('nome_arquivo')}")
                print("\nPara verificar o status da transcrição, use:")
                print(f"curl -H 'X-API-Key: {args.api_key}' {args.url}/transcribe/status/{result.get('id')}")
        else:
            print(f"Erro na requisição: {response.status_code} - {response.text}")

if __name__ == '__main__':
    main()

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import logging
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk, filedialog

from PIL import Image, ImageTk
import cv2
import os
os.environ.setdefault("ZBAR_DEBUG", "0")
from pyzbar.pyzbar import decode
from urllib.parse import quote
import csv

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AxisCameraBarcodeScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Leitor de Códigos - Câmera Axis")
        self.root.geometry("800x600")
        
        # Configurações da câmera (serão preenchidas pelo usuário)
        self.camera_ip = ""
        self.camera_username = ""
        self.camera_password = ""
        self.scanning = False
        self.last_code = None
        self.last_scan_time = 0
        self.scan_cooldown = 30  # segundos entre leituras para evitar duplicatas
        self.current_image = None  # Para armazenar a imagem atual
        self.current_frame_cv = None  # Para armazenar o último frame OpenCV
        self.cap = None  # RTSP VideoCapture
        # Controle de duplicidade por código (tempo e presença)
        self.code_last_seen = {}      # mapa: codigo -> último timestamp visto
        self.code_last_emitted = {}   # mapa: codigo -> último timestamp emitido
        self.code_stats = {}
        self.scanned_records = []
        
        self.setup_ui()
    
    def setup_ui(self):
        # Frame de configuração
        config_frame = ttk.LabelFrame(self.root, text="Configuração da Câmera")
        config_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(config_frame, text="IP da Câmera:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.ip_entry = ttk.Entry(config_frame, width=30)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ip_entry.insert(0, "192.168.0.90")  # IP padrão
        
        ttk.Label(config_frame, text="Usuário:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.username_entry = ttk.Entry(config_frame, width=30)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)
        self.username_entry.insert(0, "root")  # Usuário padrão
        
        ttk.Label(config_frame, text="Senha:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.password_entry = ttk.Entry(config_frame, width=30, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)
        
        # Botões de controle
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        self.start_button = ttk.Button(control_frame, text="Iniciar Leitura", command=self.toggle_scanning)
        self.start_button.pack(side="left", padx=5)
        
        self.test_button = ttk.Button(control_frame, text="Testar Conexão", command=self.test_connection)
        self.test_button.pack(side="left", padx=5)
        
        self.export_button = ttk.Button(control_frame, text="Exportar Relatório", command=self.export_report)
        self.export_button.pack(side="left", padx=5)
        
        # Área de visualização
        view_frame = ttk.LabelFrame(self.root, text="Visualização")
        view_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Canvas para exibir a imagem da câmera
        self.camera_canvas = tk.Canvas(view_frame, bg="black")
        self.camera_canvas.pack(fill="both", expand=True, padx=5, pady=5)
        # Atualiza a imagem quando o canvas é redimensionado
        self.camera_canvas.bind('<Configure>', self.on_canvas_resize)
        
        # Área para exibir resultados
        result_frame = ttk.LabelFrame(self.root, text="Resultados")
        result_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, height=10)
        self.result_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Pronto")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x")
    
    def toggle_scanning(self):
        if not self.scanning:
            # Iniciar escaneamento
            self.camera_ip = self.ip_entry.get()
            self.camera_username = self.username_entry.get()
            self.camera_password = self.password_entry.get()
            
            if not all([self.camera_ip, self.camera_username, self.camera_password]):
                self.update_status("Preencha todos os campos de configuração da câmera")
                return
            
            # Abrir stream RTSP
            self.open_rtsp_stream()

            if self.cap is not None and self.cap.isOpened():
                self.scanning = True
                self.start_button.config(text="Parar Leitura")
                self.update_status("Leitura via RTSP iniciada...")
                self.code_last_seen.clear()
                self.code_last_emitted.clear()
                self.code_stats.clear()
                self.scanned_records.clear()

                # Iniciar thread de escaneamento
                self.scan_thread = threading.Thread(target=self.scan_loop)
                self.scan_thread.daemon = True
                self.scan_thread.start()
            else:
                self.update_status("Falha ao abrir stream RTSP")
        else:
            # Parar escaneamento
            self.scanning = False
            self.start_button.config(text="Iniciar Leitura")
            self.update_status("Leitura interrompida")
            # Liberar o stream
            try:
                if self.cap is not None and self.cap.isOpened():
                    self.cap.release()
            except Exception:
                pass

                
    
    def scan_loop(self):
        while self.scanning:
            try:
                # Capturar frame do stream RTSP
                frame = self.capture_frame()
                if frame is not None:
                    # Processar a imagem para encontrar códigos
                    codes = self.decode_barcodes(frame)

                    # Desenhar retângulos e textos sobre os códigos encontrados
                    annotated = self.draw_barcodes(frame.copy(), codes)

                    # Atualizar a visualização da imagem na interface
                    self.update_camera_view(annotated)
                    # Lógica de deduplicação: reemitir após cooldown, mesmo visível
                    current_time = time.time()
                    if codes:
                        # Mapear códigos visíveis no frame atual
                        visible_codes = {}
                        for code in codes:
                            try:
                                data = code.data.decode('utf-8')
                            except Exception:
                                data = str(code.data)
                            visible_codes[data] = code.type

                        # Atualizar last_seen e emitir respeitando cooldown por código
                        for data, ctype in visible_codes.items():
                            self.code_last_seen[data] = current_time

                            last_emit = self.code_last_emitted.get(data, 0)
                            if (current_time - last_emit) > self.scan_cooldown:
                                # Emite (novo ou após cooldown)
                                self.code_last_emitted[data] = current_time
                                self.last_code = data
                                self.last_scan_time = current_time
                                self.root.after(0, self.update_result, f"Tipo: {ctype}, Dados: {data}")
                                self.root.after(0, self.update_status, f"Código {ctype} detectado!")
                                try:
                                    self.record_scan(data, ctype, current_time)
                                except Exception:
                                    pass

                        # Limpeza: remover códigos não vistos há muito tempo para liberar memória
                        for data in list(self.code_last_seen.keys()):
                            last_seen = self.code_last_seen.get(data, 0)
                            if (current_time - last_seen) > (self.scan_cooldown * 2):
                                self.code_last_seen.pop(data, None)
                                self.code_last_emitted.pop(data, None)
                
                # Pequena pausa para não sobrecarregar a CPU
                time.sleep(0.05)  # Reduzido para melhorar a fluidez da visualização
                
            except Exception as e:
                logger.error(f"Erro durante o escaneamento: {e}")
                self.root.after(0, self.update_status, f"Erro: {str(e)}")
                time.sleep(2)  # Pausa antes de tentar novamente
                
    def update_camera_view(self, image):
        """Atualiza a visualização da câmera no canvas mantendo a proporção e exibindo o frame inteiro"""
        try:
            # Guardar o último frame original para reagir a redimensionamentos do canvas
            self.current_frame_cv = image

            # Dimensões do frame original
            height, width = image.shape[:2]

            # Dimensões atuais do canvas
            canvas_width = self.camera_canvas.winfo_width()
            canvas_height = self.camera_canvas.winfo_height()

            # Fallback caso o canvas ainda não tenha sido renderizado
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = max(self.camera_canvas.winfo_reqwidth(), 640)
                canvas_height = max(self.camera_canvas.winfo_reqheight(), 480)

            # Calcular escala para manter proporção e mostrar o frame inteiro
            scale_w = canvas_width / width
            scale_h = canvas_height / height
            scale = min(scale_w, scale_h)

            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))

            # Redimensionar o frame para caber no canvas sem cortar
            resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)

            # Converter para imagem Tkinter
            tk_image = self.convert_cv_to_tkinter(resized)
            if tk_image:
                self.current_image = tk_image  # evitar GC

                # Centralizar no canvas (letterbox/pillarbox conforme 4:3 ou 16:9)
                x_offset = (canvas_width - new_width) // 2
                y_offset = (canvas_height - new_height) // 2

                # Renderizar no canvas
                self.camera_canvas.delete("all")
                self.camera_canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.current_image)
                # Manter referência no próprio canvas
                self.camera_canvas.image = self.current_image
        except Exception as e:
            logger.error(f"Erro ao atualizar visualização da câmera: {e}")

    def on_canvas_resize(self, event):
        """Redesenha a imagem ao redimensionar o canvas para manter a proporção"""
        try:
            if self.current_frame_cv is not None:
                self.update_camera_view(self.current_frame_cv)
        except Exception as e:
            logger.error(f"Erro no redimensionamento do canvas: {e}")

    def build_rtsp_url(self):
        """Constroi a URL RTSP padrão para câmeras Axis com credenciais codificadas e porta padrão"""
        # Codificar caracteres especiais em usuário e senha (ex.: @, #, :, etc.)
        username_enc = quote(self.camera_username or "", safe="")
        password_enc = quote(self.camera_password or "", safe="")

        host = (self.camera_ip or "").strip()
        # Adicionar porta padrão 554 se nenhuma porta for especificada
        # Considera IPv4 comum; se houver ':' assumimos que já há porta.
        if host and ":" not in host:
            host = f"{host}:554"

        return f"rtsp://{username_enc}:{password_enc}@{host}/axis-media/media.amp"

    def open_rtsp_stream(self):
        """Abre o stream RTSP com OpenCV"""
        try:
            rtsp_url = self.build_rtsp_url()
            self.cap = cv2.VideoCapture(rtsp_url)
            if self.cap.isOpened():
                self.update_status("Stream RTSP aberto com sucesso")
            else:
                self.update_status("Falha ao abrir stream RTSP")
        except Exception as e:
            logger.error(f"Erro ao abrir RTSP: {e}")
            self.update_status(f"Erro ao abrir RTSP: {str(e)}")

    def capture_frame(self):
        """Captura um frame do stream RTSP"""
        try:
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    return frame
        except Exception as e:
            logger.error(f"Erro ao capturar frame RTSP: {e}")
        return None
    
    def decode_barcodes(self, image):
        """Decodifica códigos de barras/QR de uma imagem"""
        try:
            codes = decode(image)
            if codes:
                return codes
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            codes = decode(gray)
            if codes:
                return codes
            eq = cv2.equalizeHist(gray)
            codes = decode(eq)
            if codes:
                return codes
            _, th = cv2.threshold(eq, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            codes = decode(th)
            return codes
        except Exception as e:
            logger.error(f"Erro ao decodificar códigos: {e}")
            return []

    def record_scan(self, data, ctype, ts):
        try:
            self.scanned_records.append({"timestamp": ts, "type": ctype, "data": data})
            st = self.code_stats.get(data)
            if st is None:
                self.code_stats[data] = {"type": ctype, "first_seen": ts, "last_seen": ts, "count": 1}
            else:
                st["last_seen"] = ts
                st["count"] += 1
        except Exception:
            pass

    def generate_report(self, dir_path=None):
        try:
            if not self.scanned_records:
                self.update_result("Nenhum código lido para relatório")
                return
            ts = time.strftime("%Y%m%d-%H%M%S")
            base = dir_path or os.getcwd()
            summary_path = os.path.join(base, f"axis_codes_summary_{ts}.csv")
            detail_path = os.path.join(base, f"axis_codes_detalhado_{ts}.csv")
            with open(summary_path, "w", newline="", encoding="utf-8") as fsum:
                wsum = csv.writer(fsum)
                wsum.writerow(["data", "type", "count", "first_seen", "last_seen"])
                for data, st in self.code_stats.items():
                    first_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st["first_seen"]))
                    last_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st["last_seen"]))
                    wsum.writerow([data, st["type"], st["count"], first_str, last_str])
            with open(detail_path, "w", newline="", encoding="utf-8") as fdet:
                wdet = csv.writer(fdet)
                wdet.writerow(["timestamp", "type", "data"])
                for rec in self.scanned_records:
                    ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec["timestamp"]))
                    wdet.writerow([ts_str, rec["type"], rec["data"]])
            self.update_result(f"Relatório salvo: {summary_path}")
            self.update_result(f"Relatório detalhado salvo: {detail_path}")
            self.update_status("Relatórios gerados com sucesso")
        except Exception as e:
            try:
                self.update_status(f"Erro ao gerar relatórios: {str(e)}")
            except Exception:
                pass

    def export_report(self):
        try:
            directory = filedialog.askdirectory(mustexist=True, title="Selecionar pasta para salvar relatório")
            if directory:
                self.generate_report(dir_path=directory)
            else:
                self.update_status("Exportação cancelada")
        except Exception as e:
            try:
                self.update_status(f"Erro ao exportar relatório: {str(e)}")
            except Exception:
                pass
    def draw_barcodes(self, frame, codes):
        """Desenha retângulos e textos sobre os códigos detectados no frame"""
        try:
            for code in codes:
                # Extrair retângulo
                rect = getattr(code, 'rect', None)
                if rect is not None:
                    # rect pode ser tupla (x, y, w, h) ou objeto com atributos
                    try:
                        x, y, w, h = rect
                    except Exception:
                        x, y, w, h = rect.left, rect.top, rect.width, rect.height

                    # Desenhar retângulo
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    # Preparar texto
                    code_data = code.data.decode('utf-8') if hasattr(code, 'data') else ''
                    code_type = code.type if hasattr(code, 'type') else ''
                    label = f"{code_data} ({code_type})"

                    # Posicionar texto acima do retângulo, com clamp para não sair do topo
                    text_y = y - 10 if y - 10 > 0 else y + h + 20
                    cv2.putText(frame, label, (x, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        except Exception as e:
            logger.error(f"Erro ao desenhar códigos: {e}")
        return frame
            
    def convert_cv_to_tkinter(self, cv_image):
        """Converte uma imagem OpenCV para formato compatível com Tkinter"""
        try:
            # Converter de BGR para RGB (OpenCV usa BGR, Tkinter usa RGB)
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            
            # Converter para formato PIL
            pil_image = Image.fromarray(rgb_image)
            
            # Converter para formato Tkinter
            tk_image = ImageTk.PhotoImage(image=pil_image)
            return tk_image
        except Exception as e:
            logger.error(f"Erro ao converter imagem: {e}")
            return None
    
    def test_connection(self):
        """Testa a conexão com a câmera via RTSP"""
        self.camera_ip = self.ip_entry.get()
        self.camera_username = self.username_entry.get()
        self.camera_password = self.password_entry.get()

        if not all([self.camera_ip, self.camera_username, self.camera_password]):
            self.update_status("Preencha todos os campos de configuração da câmera")
            return

        self.update_status("Testando conexão RTSP com a câmera...")

        try:
            rtsp_url = self.build_rtsp_url()
            cap = cv2.VideoCapture(rtsp_url)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    self.update_status("Conexão RTSP bem-sucedida!")
                    self.update_result(f"Teste RTSP OK - Resolução: {w}x{h}")
                else:
                    self.update_status("Conectado, mas não retornou frame")
            else:
                self.update_status("Falha ao conectar via RTSP")
        except Exception as e:
            self.update_status(f"Erro de conexão RTSP: {str(e)}")
        finally:
            try:
                if 'cap' in locals() and cap.isOpened():
                    cap.release()
            except Exception:
                pass
    
    def update_status(self, message):
        """Atualiza a barra de status"""
        self.status_var.set(message)
    
    def update_result(self, message):
        """Adiciona uma mensagem à área de resultados"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.result_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.result_text.see(tk.END)  # Rolar para o final

def main():
    root = tk.Tk()
    app = AxisCameraBarcodeScannerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

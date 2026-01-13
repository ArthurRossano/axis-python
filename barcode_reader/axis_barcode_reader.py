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
        self.connected = False  # Estado da conexão RTSP
        self.scanning = False   # Estado da leitura de códigos
        self.last_code = None
        self.last_scan_time = 0
        self.scan_cooldown = 30  # segundos entre leituras para evitar duplicatas
        self.current_image = None  # Para armazenar a imagem atual
        self.current_frame_cv = None  # Para armazenar o último frame OpenCV
        self.cap = None  # RTSP VideoCapture
        
        # Variáveis para controle de thread de captura (baixa latência)
        self.frame_lock = threading.Lock()
        self.new_frame_event = threading.Event()
        self.latest_frame = None
        
        # Controle de duplicidade por código (tempo e presença)
        self.code_last_seen = {}      # mapa: codigo -> último timestamp visto
        self.code_last_emitted = {}   # mapa: codigo -> último timestamp emitido
        self.code_stats = {}
        self.scanned_records = []
        self.live_report_path = None
        self.live_report_file = None
        self.live_report_writer = None
        
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
        
        ttk.Label(config_frame, text="Intervalo (s):").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.interval_entry = ttk.Entry(config_frame, width=30)
        self.interval_entry.grid(row=3, column=1, padx=5, pady=5)
        self.interval_entry.insert(0, "30")  # Intervalo padrão
        
        # Botões de controle
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        self.connect_button = ttk.Button(control_frame, text="Conectar Câmera", command=self.toggle_connection)
        self.connect_button.pack(side="left", padx=5)

        self.start_button = ttk.Button(control_frame, text="Iniciar Leitura", command=self.toggle_scanning, state="disabled")
        self.start_button.pack(side="left", padx=5)
        
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
        
        live_frame = ttk.LabelFrame(self.root, text="Leituras (tempo real)")
        live_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.live_tree = ttk.Treeview(live_frame, columns=("Data", "Horário", "Código", "Quantidade"), show="headings")
        self.live_tree.heading("Data", text="Data")
        self.live_tree.heading("Horário", text="Horário")
        self.live_tree.heading("Código", text="Código")
        self.live_tree.heading("Quantidade", text="Quantidade")
        self.live_tree.column("Data", width=100, anchor="center")
        self.live_tree.column("Horário", width=90, anchor="center")
        self.live_tree.column("Código", width=300, anchor="w")
        self.live_tree.column("Quantidade", width=100, anchor="center")
        self.live_tree.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        live_scroll = ttk.Scrollbar(live_frame, orient="vertical", command=self.live_tree.yview)
        self.live_tree.configure(yscrollcommand=live_scroll.set)
        live_scroll.pack(side="right", fill="y")
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Pronto")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        self.status_bar.pack(side="bottom", fill="x")
    
    def toggle_connection(self):
        if not self.connected:
            # Conectar
            self.camera_ip = self.ip_entry.get()
            self.camera_username = self.username_entry.get()
            self.camera_password = self.password_entry.get()
            
            if not all([self.camera_ip, self.camera_username, self.camera_password]):
                self.update_status("Preencha todos os campos de configuração da câmera")
                return

            self.open_rtsp_stream()
            
            if self.cap is not None and self.cap.isOpened():
                self.connected = True
                self.connect_button.config(text="Desconectar Câmera")
                self.start_button.config(state="normal")
                self.update_status("Conectado à câmera. Visualização iniciada.")
                
                # Iniciar thread de captura (buffer cleaning) para baixa latência
                self.capture_thread = threading.Thread(target=self.capture_loop)
                self.capture_thread.daemon = True
                self.capture_thread.start()

                # Iniciar thread de vídeo (processamento e display)
                self.video_thread = threading.Thread(target=self.video_loop)
                self.video_thread.daemon = True
                self.video_thread.start()
            else:
                self.update_status("Falha ao conectar à câmera")
        else:
            # Desconectar
            self.connected = False
            self.scanning = False
            self.connect_button.config(text="Conectar Câmera")
            self.start_button.config(text="Iniciar Leitura", state="disabled")
            self.update_status("Desconectado da câmera")
            self.stop_live_report()
            
            # Liberar recursos
            try:
                if self.cap is not None and self.cap.isOpened():
                    self.cap.release()
            except Exception:
                pass
            self.camera_canvas.delete("all")

    def toggle_scanning(self):
        if not self.connected:
            self.update_status("É necessário conectar à câmera primeiro")
            return

        if not self.scanning:
            # Iniciar escaneamento (apenas ativa a flag de processamento)
            try:
                interval_val = float(self.interval_entry.get())
                if interval_val < 0:
                    raise ValueError
                self.scan_cooldown = interval_val
            except ValueError:
                self.update_status("Intervalo inválido. Deve ser um número positivo.")
                return

            self.scanning = True
            self.start_button.config(text="Parar Leitura")
            self.update_status("Leitura de códigos iniciada...")
            
            # Resetar contadores se necessário ou manter histórico? 
            # Geralmente reiniciar sessão de leitura limpa cache recente, mas mantém histórico.
            # Vamos limpar apenas last_seen para permitir releitura imediata se cooldown permitir
            self.code_last_seen.clear()
            self.code_last_emitted.clear()
            self.start_live_report()
            self.clear_live_view()
            
        else:
            # Parar escaneamento
            self.scanning = False
            self.start_button.config(text="Iniciar Leitura")
            self.update_status("Leitura de códigos pausada (visualização ativa)")
            self.stop_live_report()
    
    def capture_loop(self):
        """Loop dedicado para ler frames o mais rápido possível e manter buffer vazio"""
        while self.connected:
            try:
                if self.cap is not None and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        with self.frame_lock:
                            self.latest_frame = frame
                        self.new_frame_event.set()
                    else:
                        time.sleep(0.01)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"Erro no loop de captura: {e}")
                time.sleep(0.1)

    def video_loop(self):
        while self.connected:
            try:
                # Capturar frame do stream RTSP (agora sincronizado com evento de nova imagem)
                frame = self.capture_frame()
                
                if frame is not None:
                    # Se estiver escaneando, processa o frame
                    if self.scanning:
                        # Processar a imagem para encontrar códigos
                        codes = self.decode_barcodes(frame)
                        # Desenhar retângulos e textos sobre os códigos encontrados
                        annotated = self.draw_barcodes(frame.copy(), codes)
                        # Atualizar a visualização com anotações
                        self.update_camera_view(annotated)
                        
                        # Lógica de processamento dos códigos encontrados
                        self.process_codes(codes)
                    else:
                        # Apenas visualização, sem processamento pesado
                        self.update_camera_view(frame)
                else:
                    # Se não houver frame novo (timeout), loop continua
                    pass
                
                # Sem sleep fixo aqui, pois o ritmo é ditado pelo capture_frame (wait)
                
            except Exception as e:
                logger.error(f"Erro no loop de vídeo: {e}")
                time.sleep(1)

    def process_codes(self, codes):
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

            # Limpeza: remover códigos não vistos há muito tempo
            for data in list(self.code_last_seen.keys()):
                last_seen = self.code_last_seen.get(data, 0)
                if (current_time - last_seen) > (self.scan_cooldown * 2):
                    self.code_last_seen.pop(data, None)
                    self.code_last_emitted.pop(data, None)

                
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
            
            # Otimização para baixa latência: buffer pequeno
            try:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
                
            if self.cap.isOpened():
                self.update_status("Stream RTSP aberto com sucesso")
            else:
                self.update_status("Falha ao abrir stream RTSP")
        except Exception as e:
            logger.error(f"Erro ao abrir RTSP: {e}")
            self.update_status(f"Erro ao abrir RTSP: {str(e)}")

    def capture_frame(self):
        """Captura o frame mais recente da thread de captura"""
        try:
            # Espera por um novo frame (com timeout para não travar a UI se a câmera cair)
            if self.new_frame_event.wait(timeout=0.2):
                self.new_frame_event.clear()
                with self.frame_lock:
                    if self.latest_frame is not None:
                        return self.latest_frame
        except Exception as e:
            logger.error(f"Erro ao recuperar frame do buffer: {e}")
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
        try:
            self.append_live_record(data, ts)
        except Exception:
            pass

    def generate_report(self, dir_path=None):
        try:
            if not self.scanned_records:
                self.update_result("Nenhum código lido para relatório")
                return
            ts = time.strftime("%Y%m%d-%H%M%S")
            base = dir_path or os.getcwd()
            # Gerar apenas o relatório detalhado conforme solicitado
            report_path = os.path.join(base, f"axis_codes_{ts}.csv")
            
            with open(report_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Data", "Horário", "Código", "Quantidade"])
                for rec in self.scanned_records:
                    local_time = time.localtime(rec["timestamp"])
                    date_str = time.strftime("%d/%m/%Y", local_time)
                    time_str = time.strftime("%H:%M:%S", local_time)
                    count = self.code_stats[rec["data"]]["count"]
                    writer.writerow([date_str, time_str, rec["data"], count])
            
            self.update_result(f"Relatório salvo: {report_path}")
            self.update_status("Relatório gerado com sucesso")
        except Exception as e:
            try:
                self.update_status(f"Erro ao gerar relatórios: {str(e)}")
            except Exception:
                pass
    
    def start_live_report(self, dir_path=None):
        try:
            ts = time.strftime("%Y%m%d-%H%M%S")
            base = dir_path or os.getcwd()
            self.live_report_path = os.path.join(base, f"axis_codes_live_{ts}.csv")
            self.live_report_file = open(self.live_report_path, "w", newline="", encoding="utf-8")
            self.live_report_writer = csv.writer(self.live_report_file)
            self.live_report_writer.writerow(["Data", "Horário", "Código", "Quantidade"])
            try:
                self.live_report_file.flush()
                os.fsync(self.live_report_file.fileno())
            except Exception:
                pass
            self.update_result(f"Relatório em tempo real: {self.live_report_path}")
            self.update_status("Relatório atualizado a cada leitura")
        except Exception as e:
            self.live_report_path = None
            self.live_report_file = None
            self.live_report_writer = None
            try:
                self.update_status(f"Erro ao iniciar relatório: {str(e)}")
            except Exception:
                pass
    
    def stop_live_report(self):
        try:
            if self.live_report_file:
                try:
                    self.live_report_file.flush()
                    os.fsync(self.live_report_file.fileno())
                except Exception:
                    pass
                self.live_report_file.close()
        except Exception:
            pass
        self.live_report_file = None
        self.live_report_writer = None
        self.live_report_path = None
    
    def append_live_record(self, data, ts):
        try:
            if self.live_report_writer:
                local_time = time.localtime(ts)
                date_str = time.strftime("%d/%m/%Y", local_time)
                time_str = time.strftime("%H:%M:%S", local_time)
                count = self.code_stats.get(data, {}).get("count", 1)
                self.live_report_writer.writerow([date_str, time_str, data, count])
                try:
                    self.live_report_file.flush()
                    os.fsync(self.live_report_file.fileno())
                except Exception:
                    pass
                try:
                    self.root.after(0, self.update_live_view, data, ts)
                except Exception:
                    pass
        except Exception:
            pass
    
    def clear_live_view(self):
        try:
            for i in self.live_tree.get_children():
                self.live_tree.delete(i)
        except Exception:
            pass
    
    def update_live_view(self, data, ts):
        try:
            local_time = time.localtime(ts)
            date_str = time.strftime("%d/%m/%Y", local_time)
            time_str = time.strftime("%H:%M:%S", local_time)
            count = self.code_stats.get(data, {}).get("count", 1)
            self.live_tree.insert("", "end", values=(date_str, time_str, data, count))
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

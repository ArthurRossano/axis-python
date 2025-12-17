import tkinter as tk
from tkinter import ttk, scrolledtext
from PIL import Image, ImageTk
import cv2
import os
os.environ.setdefault("ZBAR_DEBUG", "0")
from pyzbar import pyzbar
import threading
import time

class AxisCameraBarcodeScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Leitor de Códigos - Axis Camera")
        self.root.geometry("900x600")

        # Variáveis
        self.scanning = False
        self.cap = None
        self.last_codes = []  # Para armazenar códigos lidos

        # Widgets
        self.create_widgets()

    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Frame de configuração (topo)
        config_frame = ttk.LabelFrame(main_frame, text="Configuração da Câmera", padding=10)
        config_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(config_frame, text="IP (porta RTSP):").grid(row=0, column=0, sticky="w")
        self.ip_entry = ttk.Entry(config_frame, width=30)
        self.ip_entry.grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(config_frame, text="Usuário:").grid(row=1, column=0, sticky="w")
        self.username_entry = ttk.Entry(config_frame, width=30)
        self.username_entry.grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(config_frame, text="Senha:").grid(row=2, column=0, sticky="w")
        self.password_entry = ttk.Entry(config_frame, width=30, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=2)

        self.start_button = ttk.Button(config_frame, text="Iniciar Leitura", command=self.toggle_scanning)
        self.start_button.grid(row=3, column=0, columnspan=2, pady=10)

        # Frame de conteúdo (lado a lado)
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill="both", expand=True)
        
        # Frame da câmera (lado esquerdo)
        camera_frame = ttk.LabelFrame(content_frame, text="Visualização da Câmera", padding=10)
        camera_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # Canvas para a imagem da câmera (responsivo)
        self.camera_canvas = tk.Canvas(camera_frame, bg="black")
        self.camera_canvas.pack(fill="both", expand=True)
        
        # Bind para redimensionamento do canvas
        self.camera_canvas.bind('<Configure>', self.on_canvas_resize)

        # Frame dos resultados (lado direito)
        results_frame = ttk.LabelFrame(content_frame, text="Códigos Lidos", padding=10)
        results_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # Área de texto para mostrar resultados
        self.results_text = scrolledtext.ScrolledText(results_frame, wrap=tk.WORD, height=15)
        self.results_text.pack(fill="both", expand=True)

        # Frame de status (rodapé)
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill="x", pady=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="Pronto para iniciar", foreground="blue")
        self.status_label.pack()

    def update_status(self, message):
        self.status_label.config(text=message)

    def toggle_scanning(self):
        if not self.scanning:
            # Começar leitura
            self.camera_ip = self.ip_entry.get().strip()
            self.camera_username = self.username_entry.get().strip()
            self.camera_password = self.password_entry.get().strip()

            self.open_rtsp_stream()

            if hasattr(self, 'cap') and self.cap.isOpened():
                self.scanning = True
                self.start_button.config(text="Parar Leitura")
                self.update_status("Leitura iniciada")
                threading.Thread(target=self.scan_loop, daemon=True).start()
            else:
                self.update_status("Erro ao conectar ao stream RTSP")
        else:
            # Parar leitura
            self.scanning = False
            self.start_button.config(text="Iniciar Leitura")
            self.update_status("Leitura interrompida")
            if hasattr(self, 'cap') and self.cap.isOpened():
                self.cap.release()

    def open_rtsp_stream(self):
        """Abre o stream RTSP"""
        rtsp_url = f"rtsp://{self.camera_username}:{self.camera_password}@{self.camera_ip}/axis-media/media.amp"
        self.cap = cv2.VideoCapture(rtsp_url)
        if self.cap.isOpened():
            self.update_status("Stream RTSP aberto com sucesso")
        else:
            self.update_status("Falha ao abrir stream RTSP")

    def capture_frame(self):
        """Captura um frame do stream RTSP"""
        if hasattr(self, 'cap') and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                return frame
        return None

    def scan_loop(self):
        while self.scanning:
            frame = self.capture_frame()
            if frame is not None:
                barcodes = pyzbar.decode(frame)
                if not barcodes:
                    try:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        barcodes = pyzbar.decode(gray)
                        if not barcodes:
                            eq = cv2.equalizeHist(gray)
                            barcodes = pyzbar.decode(eq)
                            if not barcodes:
                                _, th = cv2.threshold(eq, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
                                barcodes = pyzbar.decode(th)
                    except Exception:
                        pass
                
                # Desenhar retângulos e texto nos códigos encontrados
                for barcode in barcodes:
                    x, y, w, h = barcode.rect
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    barcode_data = barcode.data.decode('utf-8')
                    barcode_type = barcode.type
                    cv2.putText(frame, f"{barcode_data} ({barcode_type})", (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    
                    # Adicionar código à lista de resultados
                    self.add_result(barcode_data, barcode_type)

                # Atualizar imagem no canvas (sem cortar, mantendo proporção)
                self.update_camera_display(frame)
            else:
                self.update_status("Sem frame do stream")
            self.root.update_idletasks()
            
    def on_canvas_resize(self, event):
        """Callback para quando o canvas é redimensionado"""
        # Atualizar a imagem quando o canvas for redimensionado
        if hasattr(self, 'current_frame') and self.current_frame is not None:
            self.update_camera_display(self.current_frame)

    def update_camera_display(self, frame):
        """Atualiza a exibição da câmera no canvas mantendo a proporção original"""
        if frame is not None:
            # Armazenar o frame atual para redimensionamento
            self.current_frame = frame
            
            # Obter dimensões do frame original
            height, width = frame.shape[:2]
            
            # Obter dimensões atuais do canvas
            canvas_width = self.camera_canvas.winfo_width()
            canvas_height = self.camera_canvas.winfo_height()
            
            # Se o canvas ainda não foi renderizado, usar dimensões mínimas
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 400
                canvas_height = 400
            
            # Calcular a escala para manter a proporção
            scale_width = canvas_width / width
            scale_height = canvas_height / height
            scale = min(scale_width, scale_height)
            
            # Calcular novas dimensões mantendo proporção
            new_width = int(width * scale)
            new_height = int(height * scale)
            
            # Redimensionar a imagem
            resized_frame = cv2.resize(frame, (new_width, new_height))
            
            # Converter para formato Tkinter
            rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            tk_image = ImageTk.PhotoImage(pil_image)
            
            # Calcular posição para centralizar a imagem no canvas
            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2
            
            # Limpar canvas e adicionar nova imagem
            self.camera_canvas.delete("all")
            self.camera_canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=tk_image)
            
            # Manter referência da imagem para evitar garbage collection
            self.camera_canvas.image = tk_image
        
    def add_result(self, data, barcode_type):
        """Adiciona um resultado à área de resultados"""
        timestamp = time.strftime("%H:%M:%S")
        result_text = f"[{timestamp}] {barcode_type}: {data}\n"
        
        # Verificar se não é duplicata recente
        if data not in self.last_codes:
            self.results_text.insert(tk.END, result_text)
            self.results_text.see(tk.END)  # Scroll para o final
            self.last_codes.append(data)
            
            # Manter apenas os últimos 10 códigos para evitar duplicatas
            if len(self.last_codes) > 10:
                self.last_codes.pop(0)

def main():
    root = tk.Tk()
    app = AxisCameraBarcodeScannerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

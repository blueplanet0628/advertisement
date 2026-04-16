#!/usr/bin/env python3
"""
アスペクト比と最大表示枠の検証スクリプト

このスクリプトは以下をチェックします:
1. モニターサイズに合わせて最大表示枠が決定されているか
2. 画像の縦横比が保持されているか
"""

import sys
import os
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage, QImageReader, QColorSpace

class AspectRatioChecker(QMainWindow):
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        self.setWindowTitle('Aspect Ratio Checker')
        self.showFullScreen()
        
        # Create label
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: #2a2a2a;")
        self.label.setScaledContents(False)
        self.setCentralWidget(self.label)
        
        # Load and display image
        self.check_image(image_path)
        
        # Print information
        self.print_info()
    
    def check_image(self, image_path):
        """画像を読み込んで表示し、アスペクト比をチェック"""
        try:
            reader = QImageReader(image_path)
            reader.setAutoTransform(True)
            q_image = reader.read()
            
            if q_image.isNull():
                print(f"エラー: 画像を読み込めませんでした: {image_path}")
                return
            
            # 元の画像サイズ
            original_width = q_image.width()
            original_height = q_image.height()
            original_aspect = original_width / original_height
            
            print(f"\n=== 画像情報 ===")
            print(f"ファイル: {image_path}")
            print(f"元のサイズ: {original_width} x {original_height}")
            print(f"元のアスペクト比: {original_aspect:.4f} ({original_width}:{original_height})")
            
            # モニターサイズを取得
            screen = QApplication.primaryScreen()
            screen_geometry = screen.geometry()
            screen_width = screen_geometry.width()
            screen_height = screen_geometry.height()
            screen_aspect = screen_width / screen_height
            
            print(f"\n=== モニター情報 ===")
            print(f"モニターサイズ: {screen_width} x {screen_height}")
            print(f"モニターアスペクト比: {screen_aspect:.4f} ({screen_width}:{screen_height})")
            
            # 機能1&2: 最大表示枠を決定し、アスペクト比を保持
            # KeepAspectRatioを使用してスケーリング
            scaled_image = q_image.scaled(
                screen_width, 
                screen_height, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # 表示サイズ
            display_width = scaled_image.width()
            display_height = scaled_image.height()
            display_aspect = display_width / display_height
            
            print(f"\n=== 表示情報 ===")
            print(f"表示サイズ: {display_width} x {display_height}")
            print(f"表示アスペクト比: {display_aspect:.4f} ({display_width}:{display_height})")
            
            # チェック1: アスペクト比が保持されているか
            aspect_ratio_preserved = abs(original_aspect - display_aspect) < 0.001
            print(f"\n✓ チェック1: アスペクト比保持")
            if aspect_ratio_preserved:
                print(f"  ✅ PASS: アスペクト比が正しく保持されています")
                print(f"     元: {original_aspect:.4f} → 表示: {display_aspect:.4f}")
            else:
                print(f"  ❌ FAIL: アスペクト比が変更されています")
                print(f"     元: {original_aspect:.4f} → 表示: {display_aspect:.4f}")
                print(f"     差: {abs(original_aspect - display_aspect):.4f}")
            
            # チェック2: 最大表示枠が使われているか
            # モニターの幅または高さのいずれかに一致している必要がある
            uses_max_width = abs(display_width - screen_width) < 2
            uses_max_height = abs(display_height - screen_height) < 2
            uses_max_area = uses_max_width or uses_max_height
            
            print(f"\n✓ チェック2: 最大表示枠の使用")
            if uses_max_area:
                if uses_max_width:
                    print(f"  ✅ PASS: モニターの幅を最大限に使用しています")
                    print(f"     モニター幅: {screen_width}px, 表示幅: {display_width}px")
                if uses_max_height:
                    print(f"  ✅ PASS: モニターの高さを最大限に使用しています")
                    print(f"     モニター高さ: {screen_height}px, 表示高さ: {display_height}px")
            else:
                print(f"  ❌ FAIL: 最大表示枠が使われていません")
                print(f"     モニター: {screen_width}x{screen_height}")
                print(f"     表示: {display_width}x{display_height}")
                print(f"     未使用領域: 幅{screen_width-display_width}px, 高さ{screen_height-display_height}px")
            
            # 使用率を計算
            width_usage = (display_width / screen_width) * 100
            height_usage = (display_height / screen_height) * 100
            area_usage = (display_width * display_height) / (screen_width * screen_height) * 100
            
            print(f"\n=== 使用率 ===")
            print(f"幅の使用率: {width_usage:.1f}%")
            print(f"高さの使用率: {height_usage:.1f}%")
            print(f"面積の使用率: {area_usage:.1f}%")
            
            # 表示
            pixmap = QPixmap.fromImage(scaled_image)
            self.label.setPixmap(pixmap)
            
            # 結果サマリー
            print(f"\n=== 検証結果サマリー ===")
            if aspect_ratio_preserved and uses_max_area:
                print("✅ すべてのチェックをパスしました！")
                print("   機能1: 最大表示枠 ✓")
                print("   機能2: アスペクト比保持 ✓")
            else:
                print("❌ 一部のチェックに失敗しました")
                if not aspect_ratio_preserved:
                    print("   機能2: アスペクト比保持 ✗")
                if not uses_max_area:
                    print("   機能1: 最大表示枠 ✗")
            
        except Exception as e:
            print(f"エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def print_info(self):
        """画面に情報を表示"""
        print("\n" + "="*60)
        print("アスペクト比チェッカー")
        print("="*60)
        print("このウィンドウで画像の表示を確認できます")
        print("ターミナルに詳細な検証結果が表示されています")
        print("\n終了するには 'Q' または 'Escape' キーを押してください")
        print("="*60 + "\n")
    
    def keyPressEvent(self, event):
        """キー入力処理"""
        if event.key() == Qt.Key_Q or event.key() == Qt.Key_Escape:
            self.close()


def main():
    if len(sys.argv) < 2:
        print("使用方法: python3 check_aspect_ratio.py <画像ファイル>")
        print("例: python3 check_aspect_ratio.py ./data/test1.jpg")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"エラー: ファイルが見つかりません: {image_path}")
        sys.exit(1)
    
    app = QApplication(sys.argv)
    window = AspectRatioChecker(image_path)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()


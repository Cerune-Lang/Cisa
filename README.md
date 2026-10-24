# Cisa

自作言語でCPUを作ってみたくなった。  
なんだかよく分からないけど、Ceruneに `emit-fpga` を作っても面白いかもしれないという話がある（ほんとうか？）  

ただ、いきなりFPGAに行ってもなにが必要なのか分からないので、まずはCeruneで仮想CPUを泥臭く実装してみることにした。  

そのためにCPU、命令セット、メモリ、スタック、I/Oあたりを実際に作っていくことで、DogfoodingでCeruneにはなにが足りないのかを確認できるはず、という考え方をしています。


## 現在地

いまのCisaは、32bit固定長命令を実行する小さな仮想CPUです。

```text
Cisa
├─ Machine
│  ├─ CPU
│  │  ├─ 8 x u32 General Purpose Registers
│  │  ├─ Program Counter
│  │  ├─ Stack Pointer
│  │  ├─ Zero Flag
│  │  ├─ Carry Flag
│  │  └─ Instruction Decoder
│  │
│  └─ RAM
│     ├─ 16 x u32 words
│     └─ Stack
│
└─ ROM
   └─ u32 fixed-width instructions
```

Program Counterはまだbyte addressではなく、ROM上の命令番号をそのまま持っています。

RAMも現在はbyte-addressedではなく、`u32` のword-addressed memoryです。

```text
RAM[0]
RAM[1]
...
RAM[14]
RAM[15]
```

Stackは同じRAMを使い、上端から下方向へ伸びます。

```text
empty:

sp = 16

PUSH:

sp = sp - 1
RAM[sp] = value

POP:

value = RAM[sp]
sp = sp + 1
```


## 現在のISA

命令はすべて32bit固定長です。

| 命令 | 内容 |
| --- | --- |
| `MOVI rd, imm` | 16bit即値をregisterへ入れる |
| `ADD rd, rs1, rs2` | 32bit加算 |
| `SUB rd, rs1, rs2` | 32bit減算 |
| `JMP target` | 無条件branch |
| `JZ target` | Zero flagによる条件branch |
| `LOAD rd, address` | RAMからregisterへ読む |
| `STORE rs, address` | registerからRAMへ書く |
| `PUSH reg` | registerの値をstackへ積む |
| `POP reg` | stackからregisterへ取り出す |
| `CALL target` | 次のPCをRAM stackに積んでtargetへ分岐する |
| `RET` | RAM stackから戻り先PCを復元する |
| `OUT reg` | registerの値を表示する |
| `HALT` | CPUを停止する |

ADD / SUBのwraparoundはCeruneの通常の整数演算とは少し違います。

Ceruneの整数演算はoverflow / underflowを検出して停止するため、Cisa側ではCPUとしての32bit wraparoundを明示的に実装しています。

このあたりもCeruneでCPUを作ってみると見えてくる違いのひとつです。


## 命令形式

RRR形式:

```text
31        24 23        16 15         8 7          0
+-----------+------------+-------------+------------+
|  opcode   |     rd     |     rs1     |    rs2     |
+-----------+------------+-------------+------------+
```

ADD / SUBなどで使います。

RI16形式:

```text
31        24 23        16 15                       0
+-----------+------------+--------------------------+
|  opcode   |   rd/rs    |      immediate:16        |
+-----------+------------+--------------------------+
```

MOVI / LOAD / STOREなどで使います。

J16形式:

```text
31        24 23        16 15                       0
+-----------+------------+--------------------------+
|  opcode   |   unused   |        target:16         |
+-----------+------------+--------------------------+
```

JMP / JZで使います。

R形式:

```text
31        24 23        16 15                       0
+-----------+------------+--------------------------+
|  opcode   |    reg     |          unused          |
+-----------+------------+--------------------------+
```

OUT / PUSH / POPなどで使います。


## Stack

現在のテストROMでは、stackのLIFO動作を確認しています。

人間向けに書くとこんなプログラムです。

```asm
MOVI r0, 10
PUSH r0

MOVI r0, 20
PUSH r0

POP r1
OUT r1

POP r2
OUT r2

HALT
```

実行結果:

```text
20
10
```

最後にPUSHした20が最初にPOPされ、その次に10が取り出されます。

さらにネストしたCALL / RETも試します。

```asm
CALL subroutine       ; return addressをRAM stackへ積む
OUT r3                ; サブルーチン実行後の値（12）
HALT

subroutine:
MOVI r3, 4
CALL inner
RET

inner:
MOVI r4, 8
ADD r3, r3, r4
RET
```

CALLは次の命令番号をstackへ保存して分岐し、RETは保存されたPCへ戻ります。ROM外へのCALL、空stackでのRET、ROM外の戻り先、満杯stackでのCALLを検出して停止します。これはCisaのゲスト命令であり、Cerune本体の再帰には依存しません。

現在のROMはLIFO検証とネストしたCALL / RETの両方を実行します。期待する出力は次の通りです。

```text
20
10
12
```

検証時は `cerune check src/cpu.ceru` の後、IR・MIR・SSA・VMの各実行で同じ出力になることを確認します。変更前のLIFO出力 `20` と `10` も維持します。なおCisaのstackは16 wordで、CALLの戻り先とPUSHしたデータは同じRAMを使います。呼出規約や任意のプログラムのstack安全性を提供するものではありません。

## CeruneのDogfooding

CisaはCeruneそのもののDogfoodingでもあります。

現在は同じCisaプログラムを、Ceruneの複数の実行経路で動かして結果を比較できます。

```powershell
cerune check src/cpu.ceru

cerune run src/cpu.ceru
cerune run-mir src/cpu.ceru
cerune run-mir src/cpu.ceru --ssa
cerune run-vm src/cpu.ceru
```

現在のstack / CALL / RETテストで期待する共通結果は次の通りです。

```text
20
10
12
```

つまりざっくり、

```text
Cisa
  ↓
Machine state
  ↓
CPU + RAM + Stack
  ↓
Cerune
  ├─ IR
  ├─ MIR
  ├─ SSA
  └─ VM
```

という経路で同じCPUを観察できます。

Cisaを育てながらCerune側の表現や実行経路も育てて、両方をDogfoodingしていく予定です。


## やりたいこと

最終的には、Cerune上で小さなコンピュータを一通り作ってみたいです。

```text
Cisa
├─ CPU
│  ├─ Registers
│  ├─ Program Counter
│  ├─ Stack Pointer
│  ├─ ALU
│  ├─ Flags
│  └─ Instruction Decoder
│
├─ ISA
│  ├─ Arithmetic
│  ├─ Bit operations
│  ├─ Branch
│  ├─ Load / Store
│  ├─ Push / Pop
│  ├─ Call / Return（基本命令は実装済み）
│  └─ I/O
│
├─ Memory
│  ├─ ROM
│  ├─ RAM
│  └─ Stack
│
├─ Devices
│  ├─ Timer
│  ├─ Controller Input
│  ├─ Framebuffer
│  └─ Sound?
│
├─ Tooling
│  ├─ Assembler
│  ├─ Debug / Trace
│  └─ ROM image
│
└─ Software
   ├─ Boot ROM
   ├─ Runtime / small OS?
   └─ Games / Programs
```

まずは32bit程度の小さな仮想CPUとして作っていく予定です。

CPUだけで終わらず、RAM、スタック、割り込み、タイマー、画面、入力なども実装して、最終的には小さな仮想ゲーム機くらいまで持っていけたら面白そうです。

その過程でCerune側に必要になった機能は、実際の用途を見ながら追加していきます。

そして、もし本当にCeruneからハードウェアを生成できそうなら、

```text
Cisa
  ↓
Cerune
  ↓
FPGA向けの何か
  ↓
Verilog?
  ↓
FPGA
```

みたいなところまで行ってみたいです。

今のところ、そこまで本当に行けるのかは分かりません。  
その確認も含めてCisaを作ります。


## 名前の由来

Cerune ISA から Cisa。

## CALL / RET の回帰テスト

正常系（`20\n10\n12\n`）と4つの異常系（CALL範囲外、stack overflow、空stack RET、RET戻り先範囲外）を、IR / MIR / SSA / VM の4経路で自動検証します。

```powershell
python scripts/check_cpu.py --binary cerune
python -m unittest discover -s tests -v
```

`scripts/check_cpu.py` は `src/cpu.ceru` を変更せず、一時ディレクトリに5つのケースを作成します。各ケースについて `cerune check` と4経路の終了コード・標準出力・標準エラーを検査します。GitHub Actionsも同じコマンドを実行します。

**注意:** 現在は17命令のデモROMを対象とした回帰テストです。デモROMを変更した場合は、テスト側の期待命令とケースを更新してください。CPUの内部PC/SP/RAMの値そのものを検証するものではありません。

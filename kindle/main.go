package main

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	defaultDisplaySeconds = 30
	defaultConfigPath     = "config"
	defaultImageDir       = "."
	defaultInputDevice    = "/dev/input/event1"
	defaultTouchWidth     = 599
	defaultTouchHeight    = 799
	longPressDuration     = 2 * time.Second
	quitZoneX             = 140
	quitZoneY             = 140
)

var commandCandidates = map[string][]string{
	"fbink":         {"/usr/bin/fbink", "/usr/sbin/fbink"},
	"eips":          {"/usr/bin/eips"},
	"stop":          {"/usr/sbin/stop", "/sbin/stop"},
	"start":         {"/usr/sbin/start", "/sbin/start"},
	"lipc-set-prop": {"/usr/bin/lipc-set-prop"},
}

type config struct {
	DisplaySeconds int
	ImageDir       string
	InputDevice    string
	TouchWidth     int
	TouchHeight    int
}

type app struct {
	cfg          config
	images       []string
	index        int
	imageDir     string
	currentHash  string
	lastRendered string
	showingNoPic bool
	quitting     bool
	mu           sync.Mutex
}

type touchEvent struct {
	X        int
	Y        int
	Pressed  bool
	Released bool
}

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)

	configPath := envOrDefault("KINDLE_DASHBOARD_CONFIG", defaultConfigPath)
	baseDir := envOrDefault("KINDLE_DASHBOARD_BASE", ".")

	cfg := defaultConfig()
	if err := loadConfig(configPath, &cfg); err != nil {
		log.Printf("load config: %v", err)
	}

	imageDir := resolvePath(baseDir, cfg.ImageDir)
	log.Printf("using config=%s image_dir=%s", configPath, imageDir)

	images, err := discoverImages(imageDir)
	if err != nil {
		log.Fatalf("discover images: %v", err)
	}

	a := &app{
		cfg:      cfg,
		images:   images,
		imageDir: imageDir,
	}

	if err := runCommand("stop", "framework"); err != nil {
		log.Printf("stop framework: %v", err)
	}
	if err := runCommand("lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "1"); err != nil {
		log.Printf("disable screensaver: %v", err)
	}
	defer func() {
		if err := runCommand("lipc-set-prop", "com.lab126.powerd", "preventScreenSaver", "0"); err != nil {
			log.Printf("enable screensaver: %v", err)
		}
		if a.isQuitting() {
			return
		}
		if err := runCommand("start", "framework"); err != nil {
			log.Printf("start framework: %v", err)
		}
	}()

	log.Printf("initial images found: %d", len(a.images))
	log.Printf("about to render initial screen")
	if err := a.showCurrent(true); err != nil {
		log.Fatalf("initial display failed: %v", err)
	}
	log.Printf("initial screen rendered")

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	signalCh := make(chan os.Signal, 2)
	signal.Notify(signalCh, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signalCh)

	touchCh := make(chan touchEvent, 8)
	errCh := make(chan error, 1)

	go func() {
		errCh <- readTouchEvents(ctx, cfg.InputDevice, cfg.TouchWidth, cfg.TouchHeight, touchCh)
	}()

	ticker := time.NewTicker(time.Duration(cfg.DisplaySeconds) * time.Second)
	defer ticker.Stop()

	var pressStart time.Time
	var pressX int
	var pressY int

	for {
		select {
		case <-ticker.C:
			if a.isQuitting() {
				return
			}
			if err := a.onTick(); err != nil {
				log.Printf("display next image: %v", err)
			}
		case evt := <-touchCh:
			if evt.Pressed {
				pressStart = time.Now()
				pressX = evt.X
				pressY = evt.Y
				continue
			}

			if !evt.Released || pressStart.IsZero() {
				continue
			}

			held := time.Since(pressStart)
			startX := pressX
			startY := pressY
			pressStart = time.Time{}

			if held >= longPressDuration && inQuitZone(startX, startY) {
				if err := a.quit(); err != nil {
					log.Printf("quit failed: %v", err)
				}
				return
			}

			if err := a.nextImage(); err != nil {
				log.Printf("touch next image: %v", err)
			}
			ticker.Reset(time.Duration(cfg.DisplaySeconds) * time.Second)
		case sig := <-signalCh:
			log.Printf("received signal: %s", sig)
			if err := a.quit(); err != nil {
				log.Printf("signal quit failed: %v", err)
			}
			return
		case err := <-errCh:
			if err != nil && !errors.Is(err, context.Canceled) {
				log.Fatalf("touch reader failed: %v", err)
			}
			return
		}
	}
}

func defaultConfig() config {
	return config{
		DisplaySeconds: defaultDisplaySeconds,
		ImageDir:       defaultImageDir,
		InputDevice:    defaultInputDevice,
		TouchWidth:     defaultTouchWidth,
		TouchHeight:    defaultTouchHeight,
	}
}

func loadConfig(path string, cfg *config) error {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil
		}
		return err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNumber := 0
	for scanner.Scan() {
		lineNumber++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return fmt.Errorf("config line %d: expected key=value", lineNumber)
		}

		key = strings.TrimSpace(strings.ToLower(key))
		value = strings.TrimSpace(value)

		switch key {
		case "display_seconds":
			v, err := strconv.Atoi(value)
			if err != nil || v <= 0 {
				return fmt.Errorf("config line %d: invalid display_seconds", lineNumber)
			}
			cfg.DisplaySeconds = v
		case "image_dir":
			if value == "" {
				return fmt.Errorf("config line %d: image_dir is empty", lineNumber)
			}
			cfg.ImageDir = value
		case "input_device":
			if value == "" {
				return fmt.Errorf("config line %d: input_device is empty", lineNumber)
			}
			cfg.InputDevice = value
		case "touch_width":
			v, err := strconv.Atoi(value)
			if err != nil || v <= 0 {
				return fmt.Errorf("config line %d: invalid touch_width", lineNumber)
			}
			cfg.TouchWidth = v
		case "touch_height":
			v, err := strconv.Atoi(value)
			if err != nil || v <= 0 {
				return fmt.Errorf("config line %d: invalid touch_height", lineNumber)
			}
			cfg.TouchHeight = v
		default:
			log.Printf("ignoring unknown config key %q", key)
		}
	}

	return scanner.Err()
}

func discoverImages(dir string) ([]string, error) {
	entries, err := filepath.Glob(filepath.Join(dir, "db_*.png"))
	if err != nil {
		return nil, err
	}

	sort.Strings(entries)
	return entries, nil
}

func (a *app) showCurrent(force bool) error {
	a.mu.Lock()
	if len(a.images) == 0 {
		shouldRender := force || !a.showingNoPic
		if shouldRender {
			a.showingNoPic = true
			a.lastRendered = ""
			a.currentHash = ""
		}
		a.mu.Unlock()
		if !shouldRender {
			return nil
		}
		return runCommand("fbink", "-q", "-c", "-f", "-m", "No Pic")
	}

	image := a.images[a.index]
	a.showingNoPic = false
	a.mu.Unlock()

	hash, err := fileHash(image)
	if err != nil {
		return err
	}

	a.mu.Lock()
	shouldRender := force || a.lastRendered != image || a.currentHash != hash
	if shouldRender {
		a.lastRendered = image
		a.currentHash = hash
	}
	a.mu.Unlock()

	if !shouldRender {
		return nil
	}

	return runCommand("fbink", "-q", "-c", "-f", "-i", image)
}

func (a *app) nextImage() error {
	if err := a.refreshImages(); err != nil {
		return err
	}

	a.mu.Lock()
	if len(a.images) == 0 {
		a.mu.Unlock()
		return a.showCurrent(false)
	}
	a.index = (a.index + 1) % len(a.images)
	a.mu.Unlock()
	return a.showCurrent(true)
}

func (a *app) onTick() error {
	if err := a.refreshImages(); err != nil {
		return err
	}

	a.mu.Lock()
	imageCount := len(a.images)
	a.mu.Unlock()

	if imageCount <= 1 {
		return a.showCurrent(false)
	}

	return a.nextImage()
}

func (a *app) refreshImages() error {
	images, err := discoverImages(a.imageDir)
	if err != nil {
		return err
	}

	a.mu.Lock()
	defer a.mu.Unlock()

	if len(images) == 0 {
		a.images = nil
		a.index = 0
		return nil
	}

	if len(a.images) == 0 {
		a.images = images
		a.index = 0
		return nil
	}

	currentImage := a.images[a.index]
	a.images = images

	idx := sort.SearchStrings(images, currentImage)
	if idx < len(images) && images[idx] == currentImage {
		a.index = idx
		return nil
	}

	if a.index >= len(images) {
		a.index = 0
	}
	return nil
}

func (a *app) quit() error {
	a.mu.Lock()
	if a.quitting {
		a.mu.Unlock()
		return nil
	}
	a.quitting = true
	a.mu.Unlock()

	if err := runCommand("eips", "10", "12", "quiting dashboard"); err != nil {
		log.Printf("eips quit message: %v", err)
	}

	return runCommand("start", "framework")
}

func (a *app) isQuitting() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.quitting
}

func inQuitZone(x, y int) bool {
	return x >= 0 && x <= quitZoneX && y >= 0 && y <= quitZoneY
}

func runCommand(name string, args ...string) error {
	resolved, err := resolveCommand(name)
	if err != nil {
		return err
	}
	cmd := exec.Command(resolved, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func resolveCommand(name string) (string, error) {
	if strings.Contains(name, "/") {
		return name, nil
	}
	if path, err := exec.LookPath(name); err == nil {
		return path, nil
	}
	if candidates, ok := commandCandidates[name]; ok {
		for _, candidate := range candidates {
			if _, err := os.Stat(candidate); err == nil {
				return candidate, nil
			}
		}
	}
	return "", fmt.Errorf("command not found: %s", name)
}

func envOrDefault(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}

func resolvePath(baseDir, target string) string {
	if filepath.IsAbs(target) {
		return target
	}
	return filepath.Join(baseDir, target)
}

func readTouchEvents(ctx context.Context, devicePath string, maxX, maxY int, out chan<- touchEvent) error {
	file, err := os.Open(devicePath)
	if err != nil {
		return err
	}
	defer file.Close()

	go func() {
		<-ctx.Done()
		_ = file.Close()
	}()

	if err := grabInputDevice(file); err != nil {
		return fmt.Errorf("grab input device: %w", err)
	}
	defer func() {
		if err := ungrabInputDevice(file); err != nil {
			log.Printf("ungrab input device: %v", err)
		}
	}()

	type rawInputEvent struct {
		Sec   int32
		Usec  int32
		Type  uint16
		Code  uint16
		Value int32
	}

	const (
		evSyn = 0x00
		evKey = 0x01
		evAbs = 0x03

		synReport     = 0
		btnTouch      = 0x14a
		absMTX        = 0x35
		absMTY        = 0x36
		absMTTracking = 0x39
	)

	var (
		curX            int
		curY            int
		haveX           bool
		haveY           bool
		isPressed       bool
		trackingActive  bool
		pendingPressed  bool
		pendingReleased bool
		event           rawInputEvent
	)

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if err := binary.Read(file, binary.LittleEndian, &event); err != nil {
			if errors.Is(err, os.ErrClosed) || errors.Is(err, context.Canceled) {
				return ctx.Err()
			}
			return err
		}

		switch event.Type {
		case evAbs:
			switch event.Code {
			case absMTX:
				curX = clamp(int(event.Value), 0, maxX)
				haveX = true
			case absMTY:
				curY = clamp(int(event.Value), 0, maxY)
				haveY = true
			case absMTTracking:
				if event.Value >= 0 {
					trackingActive = true
				} else {
					trackingActive = false
					pendingReleased = true
				}
			}
		case evKey:
			if event.Code == btnTouch {
				isPressed = event.Value != 0
				if isPressed {
					pendingPressed = true
				} else {
					pendingReleased = true
				}
			}
		case evSyn:
			if event.Code != synReport {
				continue
			}

			if pendingPressed && (haveX || haveY) {
				select {
				case out <- touchEvent{X: curX, Y: curY, Pressed: true}:
				case <-ctx.Done():
					return ctx.Err()
				}
				pendingPressed = false
			}

			if trackingActive && (haveX || haveY) {
				pendingReleased = false
			}

			if pendingReleased {
				select {
				case out <- touchEvent{X: curX, Y: curY, Released: true}:
				case <-ctx.Done():
					return ctx.Err()
				}
				pendingReleased = false
				pendingPressed = false
			}

			if !haveX && !haveY {
				continue
			}
			haveX = false
			haveY = false
		}
	}
}

func fileHash(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", hash.Sum(nil)), nil
}

func clamp(v, minV, maxV int) int {
	if v < minV {
		return minV
	}
	if v > maxV {
		return maxV
	}
	return v
}

func grabInputDevice(file *os.File) error {
	const evGrab = 1074021776
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, file.Fd(), uintptr(evGrab), 1)
	if errno != 0 {
		return errno
	}
	return nil
}

func ungrabInputDevice(file *os.File) error {
	const evGrab = 1074021776
	_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, file.Fd(), uintptr(evGrab), 0)
	if errno != 0 {
		return errno
	}
	return nil
}

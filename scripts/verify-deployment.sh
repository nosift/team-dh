#!/bin/bash
# Zeabur 部署验证脚本

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
DOMAIN="${1:-your-domain.zeabur.app}"

echo "=========================================="
echo "Zeabur 部署验证"
echo "=========================================="
echo "域名: $DOMAIN"
echo ""

# 1. 检查服务是否可访问
echo -n "1. 检查服务可访问性... "
if curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/" | grep -q "200"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "   提示: 服务无法访问，请检查 Zeabur 部署状态"
fi

# 2. 检查健康检查
echo -n "2. 检查健康状态... "
HEALTH=$(curl -s "https://$DOMAIN/health" 2>/dev/null)
if echo "$HEALTH" | grep -q "ok"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "   响应: $HEALTH"
fi

# 3. 检查管理后台
echo -n "3. 检查管理后台... "
if curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/admin" | grep -q "200\|302"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${RED}✗ 失败${NC}"
fi

# 4. 检查批量兑换页面
echo -n "4. 检查批量兑换页面... "
if curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/batch.html" | grep -q "200"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${YELLOW}⚠ 警告${NC}"
    echo "   提示: 批量兑换页面可能未部署"
fi

# 5. 检查用户页面
echo -n "5. 检查用户页面... "
if curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/user.html" | grep -q "200"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${YELLOW}⚠ 警告${NC}"
    echo "   提示: 用户页面可能未部署"
fi

# 6. 检查 API 响应
echo -n "6. 检查 API 响应... "
API_RESPONSE=$(curl -s "https://$DOMAIN/api/verify?code=TEST" 2>/dev/null)
if echo "$API_RESPONSE" | grep -q "success"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${YELLOW}⚠ 警告${NC}"
    echo "   响应: $API_RESPONSE"
fi

# 7. 检查响应时间
echo -n "7. 检查响应时间... "
RESPONSE_TIME=$(curl -s -o /dev/null -w "%{time_total}" "https://$DOMAIN/" 2>/dev/null)
if (( $(echo "$RESPONSE_TIME < 2.0" | bc -l) )); then
    echo -e "${GREEN}✓ 通过 (${RESPONSE_TIME}s)${NC}"
elif (( $(echo "$RESPONSE_TIME < 5.0" | bc -l) )); then
    echo -e "${YELLOW}⚠ 较慢 (${RESPONSE_TIME}s)${NC}"
else
    echo -e "${RED}✗ 超时 (${RESPONSE_TIME}s)${NC}"
fi

echo ""
echo "=========================================="
echo "验证完成"
echo "=========================================="
echo ""
echo "下一步:"
echo "1. 访问 https://$DOMAIN/ 测试兑换功能"
echo "2. 访问 https://$DOMAIN/admin 查看管理后台"
echo "3. 检查新功能是否正常显示"
echo ""
echo "如果有问题，请查看:"
echo "- Zeabur 控制台日志"
echo "- docs/ZEABUR_DEPLOYMENT.md"
echo "- docs/TROUBLESHOOTING.md"

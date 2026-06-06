// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import { Test } from "forge-std/Test.sol";
import { stdJson } from "forge-std/StdJson.sol";
import { SqrtPriceMath } from "@uniswap/v4-core/src/libraries/SqrtPriceMath.sol";
import { SwapMath } from "@uniswap/v4-core/src/libraries/SwapMath.sol";
import { TickMath } from "@uniswap/v4-core/src/libraries/TickMath.sol";

contract UniswapV4GoldenVectorsTest is Test {
  using stdJson for string;

  uint160 private constant Q96 = 79228162514264337593543950336;
  uint256 private constant Q128 = 1 << 128;
  string private constant FIXTURE_PATH = "tests/golden/uniswap_v4_vectors.json";

  function test_TickMathReferenceConstantsMatchFixture() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".fixture_version"), "aegis-vault-challenge-v1");
    assertEq(json.readString(".vectors[0].id"), "UV4-TICK-000");
    string[] memory sqrtPrices = json.readStringArray(".vectors[0].expected.sqrt_price_x96");

    assertEq(uint256(TickMath.getSqrtPriceAtTick(-887272)), _parseUint(sqrtPrices[0]));
    assertEq(uint256(TickMath.getSqrtPriceAtTick(0)), _parseUint(sqrtPrices[1]));
    assertEq(uint256(TickMath.getSqrtPriceAtTick(887272)), _parseUint(sqrtPrices[2]));
  }

  function test_SwapMathToken0ExactInWithinOneTickMatchesFixture() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[1].id"), "UV4-SWAP-001");

    (uint160 sqrtAfter, uint256 amountIn, uint256 amountOut, uint256 feeAmount) =
      SwapMath.computeSwapStep(Q96, TickMath.getSqrtPriceAtTick(-120), 1_000_000, -1000, 0);

    assertEq(uint256(sqrtAfter), _readStringUint(json, ".vectors[1].expected.sqrt_price_x96_after"));
    assertEq(amountIn, _readStringUint(json, ".vectors[1].expected.amount0_in"));
    assertEq(amountOut, _readStringUint(json, ".vectors[1].expected.amount1_out"));
    assertEq(feeAmount, 0);
    assertEq(TickMath.getTickAtSqrtPrice(sqrtAfter), int24(json.readInt(".vectors[1].expected.final_tick")));
    assertEq(_readStringUint(json, ".vectors[1].expected.active_liquidity_after"), 1_000_000);
  }

  function test_SwapMathToken1ExactInWithinOneTickMatchesFixture() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[2].id"), "UV4-SWAP-002");

    (uint160 sqrtAfter, uint256 amountIn, uint256 amountOut, uint256 feeAmount) =
      SwapMath.computeSwapStep(Q96, TickMath.getSqrtPriceAtTick(120), 1_000_000, -1000, 0);

    assertEq(uint256(sqrtAfter), _readStringUint(json, ".vectors[2].expected.sqrt_price_x96_after"));
    assertEq(amountIn, _readStringUint(json, ".vectors[2].expected.amount1_in"));
    assertEq(amountOut, _readStringUint(json, ".vectors[2].expected.amount0_out"));
    assertEq(feeAmount, 0);
    assertEq(TickMath.getTickAtSqrtPrice(sqrtAfter), int24(json.readInt(".vectors[2].expected.final_tick")));
    assertEq(_readStringUint(json, ".vectors[2].expected.active_liquidity_after"), 1_000_000);
  }

  function test_TickCrossingInputAmountsMatchFixture() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[3].id"), "UV4-TICK-001");
    assertEq(json.readString(".vectors[4].id"), "UV4-TICK-002");

    uint256 amount1ToUpperTick = SqrtPriceMath.getAmount1Delta(
      Q96,
      TickMath.getSqrtPriceAtTick(60),
      1_000_000,
      true
    );
    uint256 amount0ToLowerTick = SqrtPriceMath.getAmount0Delta(
      TickMath.getSqrtPriceAtTick(-60),
      Q96,
      1_000_000,
      true
    );

    assertEq(amount1ToUpperTick, _readStringUint(json, ".vectors[3].expected.amount_in_consumed"));
    assertEq(amount0ToLowerTick, _readStringUint(json, ".vectors[4].expected.amount_in_consumed"));
    assertEq(uint256(TickMath.getSqrtPriceAtTick(60)), _readStringUint(json, ".vectors[3].expected.sqrt_price_x96_after"));
    assertEq(uint256(TickMath.getSqrtPriceAtTick(-60)), _readStringUint(json, ".vectors[4].expected.sqrt_price_x96_after"));
    assertEq(json.readUint(".vectors[3].expected.crossed_tick"), 60);
    assertEq(json.readInt(".vectors[4].expected.crossed_tick"), -60);
    assertEq(json.readUint(".vectors[3].expected.current_tick_after_cross"), 60);
    assertEq(json.readInt(".vectors[4].expected.current_tick_after_cross"), -61);
  }

  function test_FeeGrowthFixtureMatchesReferenceArithmetic() public view {
    string memory json = vm.readFile(FIXTURE_PATH);
    assertEq(json.readString(".vectors[5].id"), "UV4-FEE-001");
    assertEq(json.readString(".vectors[6].id"), "UV4-FEE-002");

    uint256 feeGrowthForThirtyToken0 = 30 * Q128 / 1_000_000;
    assertEq(_readStringUint(json, ".vectors[5].expected.total_fee_amount0"), 30);
    assertEq(_readStringUint(json, ".vectors[5].expected.lp_fee_amount0"), 30);
    assertEq(_readStringUint(json, ".vectors[5].expected.protocol_fee_amount0"), 0);
    assertEq(_readStringUint(json, ".vectors[5].expected.fee_growth_global0_delta_x128"), feeGrowthForThirtyToken0);
    assertEq(_readStringUint(json, ".vectors[5].expected.collect_idle0_delta"), 14);

    assertEq(json.readUint(".vectors[6].expected.pool_swap_fee_pips"), 4000);
    assertEq(_readStringUint(json, ".vectors[6].expected.total_pool_fee_amount"), 40);
    assertEq(_readStringUint(json, ".vectors[6].expected.protocol_fee_amount"), 10);
    assertEq(_readStringUint(json, ".vectors[6].expected.lp_fee_amount"), 30);
    assertEq(_readStringUint(json, ".vectors[6].expected.fee_growth_global0_delta_x128"), feeGrowthForThirtyToken0);
  }

  function _readStringUint(string memory json, string memory key) private pure returns (uint256) {
    return _parseUint(json.readString(key));
  }

  function _parseUint(string memory value) private pure returns (uint256) {
    return vm.parseUint(value);
  }
}
